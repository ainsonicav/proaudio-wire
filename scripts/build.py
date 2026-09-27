#!/usr/bin/env python3
"""news.json 검사 + rss.xml 생성.

사용법:  python3 scripts/build.py
- news.json 형식을 검사하고, 문제가 있으면 목록을 출력한 뒤 실패(exit 1)합니다.
- 통과하면 rss.xml을 news.json 기준으로 새로 만듭니다.
자동화(n8n / GitHub Actions)는 news.json만 갱신한 뒤 이 스크립트를 실행하면 됩니다.
"""
import json
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://news.ainsonic.com"
RSS_LIMIT = 40
TYPES = {"신제품", "업데이트", "행사"}
# 분류와 목표 비율 (프로오디오 60 : 컨슈머오디오 10 : 레코딩소프트웨어 20 : 기타 10)
CATEGORY_RATIO = {"프로오디오": 60, "컨슈머오디오": 10, "레코딩소프트웨어": 20, "기타": 10}
REQUIRED = ["id", "date", "company", "brand", "type", "summary", "link", "category"]


def validate(items):
    errors = []
    seen = set()
    for n, it in enumerate(items):
        tag = it.get("id", f"#{n}")
        for k in REQUIRED:
            if not str(it.get(k, "")).strip():
                errors.append(f"{tag}: '{k}' 값이 비어 있음")
        if tag in seen:
            errors.append(f"{tag}: id 중복")
        seen.add(tag)
        try:
            datetime.strptime(it.get("date", ""), "%Y-%m-%d")
        except ValueError:
            errors.append(f"{tag}: date 형식 오류 ({it.get('date')!r}) — YYYY-MM-DD 필요")
        if it.get("type") not in TYPES:
            errors.append(f"{tag}: type은 {sorted(TYPES)} 중 하나여야 함 ({it.get('type')!r})")
        if it.get("category") not in CATEGORY_RATIO:
            errors.append(f"{tag}: category는 {list(CATEGORY_RATIO)} 중 하나여야 함 ({it.get('category')!r})")
        if not str(it.get("link", "")).startswith("http"):
            errors.append(f"{tag}: link가 URL이 아님")
        if len(str(it.get("summary", ""))) > 400:
            errors.append(f"{tag}: summary가 너무 김 ({len(it['summary'])}자, 최대 280자 권장)")
        # 칸 밀림 감지: 회사/브랜드 칸에 문장·URL·구분값이 들어간 경우
        for k in ("company", "brand"):
            v = str(it.get(k, ""))
            if len(v) > 60 or v.startswith("http") or v in TYPES:
                errors.append(f"{tag}: '{k}' 값이 이상함 (칸 밀림 의심): {v[:50]!r}")
    return errors


def ratio_report(items, days=7):
    """최근 N일(게시일 기준) 분류 비율. 목표보다 많은 분류를 표시."""
    today = datetime.now(timezone.utc).date()
    recent = [i for i in items if i.get("status") != "hidden" and
              0 <= (today - datetime.strptime(i["date"], "%Y-%m-%d").date()).days < days]
    lines = []
    for label, group in ((f"최근 {days}일", recent), ("전체", [i for i in items if i.get("status") != "hidden"])):
        n = len(group) or 1
        parts = []
        for cat, goal in CATEGORY_RATIO.items():
            k = sum(1 for i in group if i.get("category") == cat)
            pct = round(k * 100 / n)
            mark = " ▲초과" if cat != "프로오디오" and pct > goal else (" ▼부족" if cat == "프로오디오" and pct < goal else "")
            parts.append(f"{cat} {k}건 {pct}%(목표 {goal}%){mark}")
        lines.append(f"{label} {len(group)}건: " + " · ".join(parts))
    return lines


def build_rss(items):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # 행사 날짜가 게시일로 들어온 미래 날짜는 오늘로 취급
    pub = lambda i: min(i["date"], today)
    items = sorted(items, key=pub, reverse=True)[:RSS_LIMIT]
    now = format_datetime(datetime.now(timezone.utc), usegmt=True)
    out = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        "    <title>PRO AUDIO WIRE - 프로오디오 신제품 소식</title>",
        f"    <link>{SITE_URL}/</link>",
        f'    <atom:link href="{SITE_URL}/rss.xml" rel="self" type="application/rss+xml" />',
        "    <description>국내외 프로오디오 신제품, 펌웨어 업데이트, 공식 런칭 실시간 소식 피드</description>",
        "    <language>ko-KR</language>",
        f"    <lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        d = datetime.strptime(pub(it), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        name = it.get("productName") or it["brand"]
        title = "[{}] {} - {}".format(it["type"], it["brand"], name)
        out += [
            "",
            "    <item>",
            f"      <title>{escape(title)}</title>",
            f"      <link>{escape(it['link'])}</link>",
            f"      <description>{escape(it['summary'])}</description>",
            f"      <pubDate>{format_datetime(d, usegmt=True)}</pubDate>",
            f'      <guid isPermaLink="false">{escape(it["id"])}</guid>',
            f"      <category>{escape(it['type'])}</category>",
            f"      <category>{escape(it.get('category', ''))}</category>",
            "    </item>",
        ]
    out += ["", "  </channel>", "</rss>", ""]
    return "\n".join(out)


def main():
    items = json.loads((ROOT / "news.json").read_text(encoding="utf-8"))
    errors = validate(items)
    if errors:
        print(f"news.json 검사 실패 ({len(errors)}건):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    (ROOT / "rss.xml").write_text(build_rss(items), encoding="utf-8")
    print(f"OK: {len(items)}건 검사 통과, rss.xml 생성 (최신 {min(len(items), RSS_LIMIT)}건)")
    for line in ratio_report(items):
        print("  분류 비율 —", line)


if __name__ == "__main__":
    main()
