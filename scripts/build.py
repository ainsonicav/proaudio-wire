#!/usr/bin/env python3
"""news.json 검사 + rss.xml 생성.

사용법:
  python3 scripts/build.py              검사 + rss.xml·sitemap.xml·n/*.html·index.html 미리보기 목록 생성
  python3 scripts/build.py --brief      news.json 전체를 읽지 않고 중복 확인용 요약만 출력
  python3 scripts/build.py --add FILE   FILE(새 항목 배열)을 id 붙여 news.json 맨 앞에 넣고 빌드
- news.json 형식을 검사하고, 문제가 있으면 목록을 출력한 뒤 실패(exit 1)합니다.
  (--add는 검사를 통과할 때만 news.json에 저장합니다.)
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from pages import build_pages

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


def compute_stats(items):
    """홈 화면 '이번 주 동향' 위젯용 통계. 새 소식이 없는 날도 최근 7일/30일
    창(window)이 하루씩 밀리면서 값이 달라지므로 매일 stats.json이 바뀐다."""
    today = datetime.now(timezone.utc).date()

    def in_window(i, days):
        try:
            d = datetime.strptime(i["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            return False
        return 0 <= (today - d).days < days

    published = [i for i in items if i.get("status") != "hidden"]
    week = [i for i in published if in_window(i, 7)]
    month = [i for i in published if in_window(i, 30)]

    brand_counts = Counter((i.get("brand") or "").strip() for i in week if i.get("brand"))
    top_brands = [{"brand": b, "count": c} for b, c in brand_counts.most_common(5)]

    def cat_ratio(group):
        n = len(group) or 1
        out = []
        for cat in CATEGORY_RATIO:
            k = sum(1 for i in group if i.get("category") == cat)
            out.append({"category": cat, "count": k, "pct": round(k * 100 / n)})
        return out

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": {"week": 7, "month": 30},
        "counts": {"week": len(week), "month": len(month), "total": len(published)},
        "top_brands_week": top_brands,
        "category_ratio_week": cat_ratio(week),
        "category_ratio_month": cat_ratio(month),
    }


TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def pub(i):
    """게시일. 행사 날짜가 게시일로 들어온 미래 날짜는 오늘로 취급."""
    return min(i["date"], TODAY)


def rfc822(day):
    return format_datetime(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc), usegmt=True)


def build_rss(items):
    items = sorted((i for i in items if i.get("status") != "hidden"), key=pub, reverse=True)[:RSS_LIMIT]
    # 최신 소식 날짜 기준 → 내용이 같으면 rss.xml도 그대로 (불필요한 커밋 방지)
    now = rfc822(pub(items[0])) if items else rfc822(TODAY)
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
        name = it.get("productName") or it["brand"]
        title = "[{}] {} - {}".format(it["type"], it["brand"], name)
        out += [
            "",
            "    <item>",
            f"      <title>{escape(title)}</title>",
            f"      <link>{SITE_URL}/n/{escape(it['id'])}.html</link>",
            f"      <description>{escape(it['summary'])}</description>",
            f"      <pubDate>{rfc822(pub(it))}</pubDate>",
            f'      <guid isPermaLink="false">{escape(it["id"])}</guid>',
            f"      <category>{escape(it['type'])}</category>",
            f"      <category>{escape(it.get('category', ''))}</category>",
            "    </item>",
        ]
    out += ["", "  </channel>", "</rss>", ""]
    return "\n".join(out)


def brief(items, days=60):
    """자동 업데이트용 요약: 가장 큰 id, 분류 비율, 최근 소식의 링크·제품 (중복 확인용)."""
    nums = [int(i["id"].split("-")[-1]) for i in items if i["id"].split("-")[-1].isdigit()]
    print(f"전체 {len(items)}건, 가장 큰 id: news-{max(nums, default=0)}")
    for line in ratio_report(items):
        print("분류 비율 —", line)
    today = datetime.now(timezone.utc).date()
    print(f"최근 {days}일 소식 (id | 게시일 | 브랜드 | 제품명 | 원문):")
    for i in items:
        if (today - datetime.strptime(i["date"], "%Y-%m-%d").date()).days < days:
            print(f"{i['id']} | {i['date']} | {i['brand']} | {i.get('productName', '')} | {i['link']}")


def add(items, path):
    """새 항목 파일을 id 붙여 맨 앞에 넣음. 이미 있는 원문 링크는 건너뜀."""
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(new, dict):
        new = [new]
    links = {i["link"].rstrip("/") for i in items}
    nums = [int(i["id"].split("-")[-1]) for i in items if i["id"].split("-")[-1].isdigit()]
    n = max(nums, default=0)
    fresh = []
    for it in new:
        if str(it.get("link", "")).rstrip("/") in links:
            print(f"  건너뜀(이미 있는 원문): {it.get('brand')} — {it.get('productName')}")
            continue
        links.add(str(it.get("link", "")).rstrip("/"))
        it.setdefault("status", "published")
        fresh.append(it)
    # 국내 먼저, 그다음 프로오디오, 그다음 최신 날짜
    fresh.sort(key=lambda i: i.get("date", ""), reverse=True)
    fresh.sort(key=lambda i: (not i.get("isDomestic"), i.get("category") != "프로오디오"))
    for k, it in enumerate(fresh):
        it.pop("id", None)
        fresh[k] = {"id": f"news-{n + k + 1}", **it}
    return fresh + items, fresh


def main():
    args = sys.argv[1:]
    path = ROOT / "news.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    if args[:1] == ["--brief"]:
        brief(items)
        return
    fresh = []
    if args[:1] == ["--add"] and len(args) == 2:
        items, fresh = add(items, args[1])
    errors = validate(items)
    if errors:
        print(f"news.json 검사 실패 ({len(errors)}건):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    if fresh:
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"추가 {len(fresh)}건:")
        for it in fresh:
            print(f"  {it['id']} [{it['category']}/{it['type']}] {it['brand']} — {it.get('productName', '')}")
    (ROOT / "rss.xml").write_text(build_rss(items), encoding="utf-8")
    changed = build_pages(ROOT, items, pub)
    stats = compute_stats(items)
    (ROOT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(items)}건 검사 통과, rss.xml 생성 (최신 {min(len(items), RSS_LIMIT)}건), 검색용 파일 {changed}개 갱신, stats.json 갱신")
    for line in ratio_report(items):
        print("  분류 비율 —", line)


if __name__ == "__main__":
    main()
