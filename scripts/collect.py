#!/usr/bin/env python3
"""feeds.json에 등록한 소스에서 새 소식 '후보'를 모아 incoming/candidates.json을 만든다.

이 스크립트는 요약을 쓰지 않는다(한국어 요약은 에이전트가 한다). RSS·게시판에서
제목·링크·원문 발표일만 뽑아 후보로 남기고, 이미 news.json에 있는 링크와
브랜드+제품명이 겹치는 항목은 건너뛴다. 후보를 news.json으로 승격하는 일은
사람(또는 에이전트)이 요약을 붙여 incoming/new.json을 만드는 단계에서 한다.

사용법:
  python3 scripts/collect.py            # 수집해서 incoming/candidates.json 갱신
  python3 scripts/collect.py --dry-run  # 파일 쓰지 않고 결과만 출력
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / "feeds.json"
NEWS = ROOT / "news.json"
OUT = ROOT / "incoming" / "candidates.json"
UA = "Mozilla/5.0 (compatible; PROAUDIOWIRE-Collector/1.0; +https://news.ainsonic.com)"
MAX_AGE_DAYS = 30
MAX_TOTAL = 40
DEDUPE_DAYS = 3


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def strip_tags(s: str) -> str:
    s = re.sub(r"<!--[\s\S]*?-->", " ", s)
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    s = s.replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", s).strip()


def to_ymd(text: str) -> str:
    """RSS 날짜 문자열이나 2026-11-18 / 2026.11.18 표기를 YYYY-MM-DD로."""
    text = (text or "").strip()
    if not text:
        return ""
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return ""
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone(timedelta(hours=9))).date().isoformat()
    except (TypeError, ValueError):
        return ""


def key_of(brand: str, product: str) -> str:
    """중복 판정용 키(브랜드+제품명 정규화)."""
    s = (brand or "") + " " + (product or "")
    s = s.lower()
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rss(feed: dict) -> list[dict]:
    xml = fetch(feed["url"])
    blocks = re.findall(r"<(item|entry)[\s>][\s\S]*?</\1>", xml)
    raws = re.findall(r"<(item|entry)[\s>][\s\S]*?</\1>", xml)
    items: list[dict] = []
    for block in re.findall(r"<(?:item|entry)[\s>][\s\S]*?</(?:item|entry)>", xml)[: feed.get("maxItems", 8) + 8]:
        title = strip_tags((re.search(r"<title[^>]*>([\s\S]*?)</title>", block) or [None, ""])[1])
        link = ""
        m = re.search(r"<link[^>]*href=[\"']([^\"']+)[\"']", block)
        if m:
            link = m.group(1)
        else:
            m = re.search(r"<link>([\s\S]*?)</link>", block)
            if m:
                link = strip_tags(m.group(1))
        date_raw = ""
        for tag in ("pubDate", "published", "updated", "dc:date"):
            m = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", block)
            if m:
                date_raw = strip_tags(m.group(1))
                break
        desc = ""
        m = re.search(r"<(?:description|summary|content:encoded)>([\s\S]*?)</(?:description|summary|content:encoded)>", block)
        if m:
            desc = strip_tags(m.group(1))[:400]
        if title and link:
            items.append({"title": title, "link": link.strip(), "dateRaw": date_raw, "desc": desc})
    if not items and blocks:
        pass
    return items


def parse_html(feed: dict) -> list[dict]:
    html = fetch(feed["listUrl"])
    href_re = re.compile(feed["itemHrefPattern"])
    title_re = re.compile(feed["titlePattern"]) if feed.get("titlePattern") else None
    date_re = re.compile(feed["datePattern"]) if feed.get("datePattern") else None
    base = feed.get("baseUrl", "").rstrip("/")
    items: list[dict] = []
    pos = 0
    while len(items) < feed.get("maxItems", 8):
        m = href_re.search(html, pos)
        if not m:
            break
        start = m.start()
        block = html[start: start + 6000]
        pos = m.end()
        href = m.group(0)
        link = href if href.startswith("http") else base + ("" if href.startswith("/") else "/") + href
        title = ""
        if title_re:
            tm = title_re.search(block)
            if tm:
                title = strip_tags(tm.group(1) if tm.groups() else tm.group(0))
        if not title:
            tm = re.search(r"class=\"title[^\"]*\"[^>]*>([\s\S]{0,400}?)</div>", block)
            if tm:
                title = strip_tags(tm.group(1)).strip()
        if not title:
            tm = re.search(r">([^<>]{6,140})</(?:a|p|div|span|strong)>", block)
            title = strip_tags(tm.group(1)) if tm else ""
        title = re.sub(r"^(보도자료|안내사항|공지|뉴스)\s*[|·]?\s*", "", title).strip()
        d = ""
        if date_re:
            dm = date_re.search(block)
            if dm:
                d = to_ymd(dm.group(0))
        if not d and feed.get("detailDatePattern"):
            try:
                detail = fetch(link)
                dm = re.search(feed["detailDatePattern"], detail)
                if dm:
                    d = to_ymd(dm.group(0))
            except Exception:
                d = ""
        if title and link:
            items.append({"title": title, "link": link, "dateRaw": d, "desc": ""})
    return items


def main() -> int:
    dry = "--dry-run" in sys.argv
    feeds = json.loads(FEEDS.read_text(encoding="utf-8"))["feeds"]
    news = json.loads(NEWS.read_text(encoding="utf-8"))
    known_links = {str(i.get("link", "")).rstrip("/") for i in news}
    known_keys = {}
    for i in news:
        k = key_of(i.get("brand", ""), i.get("productName", ""))
        if k:
            known_keys.setdefault(k[:40], i.get("date", ""))

    today = date.today()
    prev = []
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = []
    seen_links = {c["link"].rstrip("/") for c in prev if c.get("link")}

    collected: list[dict] = []
    report: list[str] = []
    for feed in feeds:
        try:
            raw = parse_rss(feed) if feed["type"] == "rss" else parse_html(feed)
        except Exception as e:  # noqa: BLE001 - 소스 하나가 죽어도 나머지는 계속
            report.append(f"  ! {feed['id']}: 실패 {type(e).__name__} {str(e)[:60]}")
            continue
        kept = 0
        for it in raw:
            ymd = to_ymd(it["dateRaw"])
            if not ymd:
                continue
            try:
                gap = (today - date.fromisoformat(ymd)).days
            except ValueError:
                continue
            if gap < 0 or gap > MAX_AGE_DAYS:
                continue
            if it["link"].rstrip("/") in known_links or it["link"].rstrip("/") in seen_links:
                continue
            if feed.get("skipPattern") and re.search(feed["skipPattern"], it["title"], re.I):
                continue
            k = key_of(feed.get("defaultBrand", ""), it["title"])[:40]
            if k and k in known_keys:
                continue
            cand = {
                "source": feed["id"],
                "sourceName": feed.get("name", feed["id"]),
                "title": it["title"][:200],
                "link": it["link"],
                "sourceDate": ymd,
                "date": ymd,
                "brand": feed.get("defaultBrand", ""),
                "company": feed.get("defaultCompany", ""),
                "category": feed.get("category", "프로오디오"),
                "isDomestic": bool(feed.get("isDomestic")),
                "evidence": (it.get("desc") or "")[:400],
                "fetchedAt": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes"),
            }
            collected.append(cand)
            seen_links.add(it["link"].rstrip("/"))
            kept += 1
            if len(collected) >= MAX_TOTAL:
                break
        report.append(f"  {feed['id']}: {len(raw)}건 확인, 새 후보 {kept}건")

    collected.sort(key=lambda c: c["sourceDate"], reverse=True)
    merged = collected + [c for c in prev if c["link"].rstrip("/") not in {x["link"].rstrip("/") for x in collected}]
    merged = merged[:MAX_TOTAL]

    print("새 소식 후보 수집")
    print("\n".join(report))
    print(f"새 후보 {len(collected)}건 / 보관 {len(merged)}건")
    for c in collected[:10]:
        print(f"  - [{c['sourceName']}] {c['sourceDate']} {c['title'][:70]}")

    if dry:
        print("(--dry-run: 파일을 쓰지 않았습니다)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
