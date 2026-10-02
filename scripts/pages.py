"""검색 노출용 정적 파일 생성 (build.py가 호출).

- n/<id>.html   : 소식별 페이지 (구글이 제품명으로 찾을 수 있는 주소, 공유 미리보기용 og 태그)
- sitemap.xml   : 홈 + 소식 페이지 목록
- index.html    : <!-- PRERENDER --> 표시 사이에 최신 소식 목록을 미리 넣음
                  (자바스크립트 실행 전에도 검색엔진이 내용을 읽도록. 화면은 JS가 곧바로 다시 그림)
결과는 news.json만으로 정해지므로, 내용이 같으면 파일도 바뀌지 않습니다.
"""
import json
import re
from html import escape

SITE_URL = "https://news.ainsonic.com"
SITE_NAME = "프로오디오뉴스 PRO AUDIO WIRE"
PRERENDER_ROWS = 30
START, END = "<!-- PRERENDER:START -->", "<!-- PRERENDER:END -->"

PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="{site}" href="{base}/rss.xml">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{site}">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
{og_image}<meta property="article:published_time" content="{date}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="twitter:card" content="{card}">
<script type="application/ld+json">{ld}</script>
<style>
body{{margin:0;background:#f8fafc;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;line-height:1.7;word-break:keep-all;overflow-wrap:anywhere}}
header{{background:#fff;border-bottom:1px solid #e2e8f0}}
.hd{{max-width:760px;margin:0 auto;padding:.85rem 1rem;display:flex;align-items:center;justify-content:space-between;gap:1rem}}
.hd>a{{color:#9F1239;display:inline-flex;min-height:44px;align-items:center}}
.hd .logo{{display:block;height:24px;width:auto}}
.hd nav a{{font-size:.85rem;color:#475569;text-decoration:none;margin-left:1rem;font-weight:600}}
.hd nav a:hover{{color:#e11d48}}
.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
main{{max-width:760px;margin:0 auto;padding:1.5rem 1rem 3rem}}
.meta{{font-size:.85rem;color:#64748b;margin:0}}
.badge{{display:inline-block;background:#ffe4e6;color:#be123c;font-weight:700;font-size:.75rem;padding:.1rem .5rem;border-radius:4px;margin-right:.4rem}}
.sub-box{{margin:2rem 0 0;padding:1.1rem 1.2rem;border:1px solid #fecdd3;background:#fff1f2;border-radius:12px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.6rem 1rem}}
.sub-box p{{margin:0;font-weight:600;color:#9F1239}}
.sub-box small{{display:block;font-weight:400;color:#64748b}}
.sub-box .btn{{background:#e11d48;margin:0}}
.sub-box .btn.sub{{background:#fff;color:#9F1239;border:1px solid #fecdd3}}
h1{{font-size:1.5rem;line-height:1.35;margin:.4rem 0 1rem}}
img{{width:100%;max-height:420px;object-fit:contain;background:#fff;border:1px solid #e2e8f0;border-radius:10px}}
.summary{{font-size:1.05rem;color:#334155}}
blockquote{{margin:1rem 0;padding:.6rem .9rem;border-left:3px solid #cbd5e1;color:#64748b;font-size:.9rem;background:#fff}}
.btn{{display:inline-block;margin:.4rem .5rem .4rem 0;padding:.55rem 1rem;border-radius:8px;background:#0f172a;color:#fff;text-decoration:none;font-weight:600;font-size:.9rem}}
.btn.sub{{background:#fff;color:#0f172a;border:1px solid #cbd5e1}}
h2{{font-size:1rem;margin:2rem 0 .5rem}}
ul{{padding-left:1.1rem}} li a{{color:#0f172a}}
footer{{text-align:center;font-size:.8rem;color:#94a3b8;padding:1.5rem 1rem;border-top:1px solid #e2e8f0}}
footer a{{color:#64748b}}
</style>
</head>
<body>
<header><div class="hd"><a href="/" title="프로오디오뉴스 PRO AUDIO WIRE"><span class="sr">프로오디오뉴스 PRO AUDIO WIRE</span><svg class="logo" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="22.0 22.0 670.2 116.0"><defs><linearGradient id="glgA" gradientUnits="userSpaceOnUse" x1="24.00" y1="24.00" x2="136.00" y2="136.00"><stop offset="0" stop-color="#F43F5E"/><stop offset="1" stop-color="#E11D48"/></linearGradient></defs><path d="M24.00,80.00 a56.00,56.00 0 1,0 112.00,0 a56.00,56.00 0 1,0 -112.00,0 Z M43.04,80.00 a36.96,36.96 0 1,1 73.92,0 a36.96,36.96 0 1,1 -73.92,0 Z" fill="url(#glgA)" fill-rule="evenodd"/><path d="M51.17,80.00 Q65.59,52.61 80.00,80.00 T108.83,80.00" fill="none" stroke="url(#glgA)" stroke-width="10.64" stroke-linecap="round" stroke-linejoin="round"/><path d="M185.018 86.231H178.446V101.85499999999999H167.844V58.33099999999999H185.018Q190.226 58.33099999999999 193.822 60.12899999999999Q197.418 61.92699999999999 199.216 65.089Q201.014 68.25099999999999 201.014 72.34299999999999Q201.014 76.12499999999999 199.27800000000002 79.25599999999999Q197.542 82.38699999999999 193.946 84.309Q190.35 86.231 185.018 86.231ZM190.226 72.34299999999999Q190.226 69.73899999999999 188.738 68.31299999999999Q187.25 66.887 184.212 66.887H178.446V77.79899999999999H184.212Q187.25 77.79899999999999 188.738 76.37299999999999Q190.226 74.94699999999999 190.226 72.34299999999999Z M229.968 101.85499999999999 220.916 85.42499999999998H218.374V101.85499999999999H207.772V58.33099999999999H225.566Q230.712 58.33099999999999 234.339 60.12899999999999Q237.966 61.92699999999999 239.764 65.05799999999999Q241.562 68.189 241.562 72.03299999999999Q241.562 76.37299999999999 239.113 79.78299999999999Q236.664 83.19299999999998 231.89 84.61899999999999L241.934 101.85499999999999ZM218.374 77.92299999999999H224.946Q227.85999999999999 77.92299999999999 229.317 76.49699999999999Q230.774 75.071 230.774 72.46699999999998Q230.774 69.987 229.317 68.56099999999999Q227.85999999999999 67.13499999999999 224.946 67.13499999999999H218.374Z M247.63799999999998 79.969Q247.63799999999998 73.583 250.64499999999998 68.499Q253.652 63.41499999999999 258.767 60.56299999999999Q263.882 57.71099999999999 270.02 57.71099999999999Q276.15799999999996 57.71099999999999 281.27299999999997 60.56299999999999Q286.388 63.41499999999999 289.33299999999997 68.499Q292.27799999999996 73.583 292.27799999999996 79.969Q292.27799999999996 86.35499999999999 289.30199999999996 91.47Q286.32599999999996 96.585 281.24199999999996 99.43699999999998Q276.15799999999996 102.28899999999999 270.02 102.28899999999999Q263.882 102.28899999999999 258.767 99.43699999999998Q253.652 96.585 250.64499999999998 91.47Q247.63799999999998 86.35499999999999 247.63799999999998 79.969ZM281.49 79.969Q281.49 74.20299999999999 278.35900000000004 70.762Q275.228 67.321 270.02 67.321Q264.75 67.321 261.619 70.731Q258.488 74.14099999999999 258.488 79.969Q258.488 85.73499999999999 261.619 89.17599999999999Q264.75 92.61699999999999 270.02 92.61699999999999Q275.228 92.61699999999999 278.35900000000004 89.14499999999998Q281.49 85.67299999999999 281.49 79.969Z M340.88599999999997 94.16699999999999H324.642L322.03799999999995 101.85499999999999H310.94L326.688 58.33099999999999H338.964L354.712 101.85499999999999H343.49ZM338.15799999999996 85.98299999999999 332.76399999999995 70.04899999999999 327.43199999999996 85.98299999999999Z M371.142 58.33099999999999V84.371Q371.142 88.27699999999999 373.06399999999996 90.38499999999999Q374.986 92.493 378.706 92.493Q382.426 92.493 384.40999999999997 90.38499999999999Q386.394 88.27699999999999 386.394 84.371V58.33099999999999H396.996V84.309Q396.996 90.13699999999999 394.51599999999996 94.16699999999999Q392.036 98.19699999999999 387.851 100.243Q383.666 102.28899999999999 378.52 102.28899999999999Q373.374 102.28899999999999 369.313 100.27399999999999Q365.252 98.25899999999999 362.896 94.19799999999998Q360.54 90.13699999999999 360.54 84.309V58.33099999999999Z M444.798 80.09299999999999Q444.798 86.47899999999998 441.977 91.439Q439.156 96.39899999999999 433.97900000000004 99.12699999999998Q428.802 101.85499999999999 421.98199999999997 101.85499999999999H405.676V58.33099999999999H421.98199999999997Q428.864 58.33099999999999 434.01 61.05899999999999Q439.156 63.78699999999999 441.977 68.71599999999998Q444.798 73.64499999999998 444.798 80.09299999999999ZM434.01 80.09299999999999Q434.01 74.079 430.662 70.731Q427.31399999999996 67.38299999999998 421.3 67.38299999999998H416.278V92.67899999999999H421.3Q427.31399999999996 92.67899999999999 430.662 89.39299999999999Q434.01 86.10699999999999 434.01 80.09299999999999Z M462.59200000000004 58.33099999999999V101.85499999999999H451.99V58.33099999999999Z M469.722 79.969Q469.722 73.583 472.729 68.499Q475.736 63.41499999999999 480.851 60.56299999999999Q485.966 57.71099999999999 492.104 57.71099999999999Q498.24199999999996 57.71099999999999 503.35699999999997 60.56299999999999Q508.472 63.41499999999999 511.417 68.499Q514.362 73.583 514.362 79.969Q514.362 86.35499999999999 511.38599999999997 91.47Q508.40999999999997 96.585 503.32599999999996 99.43699999999998Q498.24199999999996 102.28899999999999 492.104 102.28899999999999Q485.966 102.28899999999999 480.851 99.43699999999998Q475.736 96.585 472.729 91.47Q469.722 86.35499999999999 469.722 79.969ZM503.574 79.969Q503.574 74.20299999999999 500.443 70.762Q497.312 67.321 492.104 67.321Q486.834 67.321 483.703 70.731Q480.572 74.14099999999999 480.572 79.969Q480.572 85.73499999999999 483.703 89.17599999999999Q486.834 92.61699999999999 492.104 92.61699999999999Q497.312 92.61699999999999 500.443 89.14499999999998Q503.574 85.67299999999999 503.574 79.969Z M595.768 58.33099999999999 584.422 101.85499999999999H571.5880000000001L564.644 73.21099999999998L557.452 101.85499999999999H544.618L533.582 58.33099999999999H544.928L551.19 90.01299999999999L558.94 58.33099999999999H570.596L578.0360000000001 90.01299999999999L584.36 58.33099999999999Z M612.9420000000001 58.33099999999999V101.85499999999999H602.3400000000001V58.33099999999999Z M644.066 101.85499999999999 635.0140000000001 85.42499999999998H632.4720000000001V101.85499999999999H621.8700000000001V58.33099999999999H639.6640000000001Q644.8100000000001 58.33099999999999 648.4370000000001 60.12899999999999Q652.0640000000001 61.92699999999999 653.8620000000001 65.05799999999999Q655.6600000000001 68.189 655.6600000000001 72.03299999999999Q655.6600000000001 76.37299999999999 653.211 79.78299999999999Q650.7620000000001 83.19299999999998 645.988 84.61899999999999L656.032 101.85499999999999ZM632.4720000000001 77.92299999999999H639.0440000000001Q641.9580000000001 77.92299999999999 643.4150000000001 76.49699999999999Q644.8720000000001 75.071 644.8720000000001 72.46699999999998Q644.8720000000001 69.987 643.4150000000001 68.56099999999999Q641.9580000000001 67.13499999999999 639.0440000000001 67.13499999999999H632.4720000000001Z M674.1360000000001 66.82499999999999V75.62899999999999H688.3340000000001V83.81299999999999H674.1360000000001V93.36099999999999H690.1940000000001V101.85499999999999H663.5340000000001V58.33099999999999H690.1940000000001V66.82499999999999Z" fill="currentColor"/></svg></a><nav><a href="/">전체 소식</a><a href="https://t.me/proaudiowire" target="_blank" rel="noopener">텔레그램</a></nav></div></header>
<main>
<article>
<p class="meta"><span class="badge">{type}</span>{category} · {brand_line} · <time datetime="{date}">{date}</time></p>
<h1>{h1}</h1>
{img}<p class="summary">{summary}</p>
{evidence}<p><a class="btn" href="{link}" target="_blank" rel="noopener noreferrer">원문 출처 보기 ↗</a><a class="btn sub" href="/?n={id}">전체 소식 목록</a></p>
<aside class="sub-box"><p>새 소식을 가장 먼저 받아보세요<small>신제품·펌웨어·행사 소식을 매일 정리합니다</small></p><span><a class="btn" href="https://t.me/proaudiowire" target="_blank" rel="noopener">텔레그램 채널</a> <a class="btn sub" href="{base}/rss.xml">RSS</a></span></aside>
</article>
{related}</main>
<footer>{site} · 프로오디오 신제품 · 업데이트 · 행사 소식 큐레이션 · 운영 <a href="https://www.ainsonic.com">아인소닉</a></footer>
</body>
</html>
"""


def visible(items):
    return [i for i in items if i.get("status") != "hidden"]


def page_url(it):
    return f"{SITE_URL}/n/{it['id']}.html"


def headline(it):
    name = it.get("productName") or it["brand"]
    if it["brand"].lower() in name.lower():
        return f"{name} {it['type']} 소식"
    return f"{it['brand']} {name} {it['type']} 소식"


def clip(s, n=155):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def render_page(it, related):
    e = lambda s: escape(str(s), quote=True)
    date = it["pub"]
    h = headline(it)
    brand_line = it["brand"] if it["company"] in (it["brand"], "") else f"{it['brand']} ({it['company']})"
    ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": h[:110],
        "description": clip(it["summary"]),
        "datePublished": date,
        "dateModified": date,
        "inLanguage": "ko",
        "mainEntityOfPage": page_url(it),
        "isBasedOn": it["link"],
        "about": {"@type": "Brand", "name": it["brand"]},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL + "/"},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL + "/"},
    }
    if it.get("imageUrl"):
        ld["image"] = [it["imageUrl"]]
    rel = ""
    if related:
        rel = "<section>\n<h2>" + e(it["brand"]) + " 다른 소식</h2>\n<ul>\n" + "".join(
            f'<li><a href="/n/{e(r["id"])}.html">{e(headline(r))}</a> <span class="meta">{e(r["pub"])}</span></li>\n'
            for r in related) + "</ul>\n</section>\n"
    img = it.get("imageUrl")
    return PAGE.format(
        title=e(f"{h} | {SITE_NAME}"),
        og_title=e(h),
        desc=e(clip(it["summary"])),
        url=e(page_url(it)),
        base=SITE_URL,
        site=SITE_NAME,
        og_image=f'<meta property="og:image" content="{e(img)}">\n' if img else f'<meta property="og:image" content="{SITE_URL}/og.jpg">\n',
        card="summary_large_image" if img else "summary",
        date=e(date),
        ld=json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"),
        type=e(it["type"]),
        category=e(it.get("category", "")),
        brand_line=e(brand_line),
        h1=e(h),
        img=f'<img src="{e(img)}" alt="{e(it.get("productName") or it["brand"])}" referrerpolicy="no-referrer" onerror="this.remove()">\n' if img else "",
        summary=e(it["summary"]),
        evidence=f'<blockquote>원문: “{e(it["evidence"])}”</blockquote>\n' if it.get("evidence") else "",
        link=e(it["link"]),
        id=e(it["id"]),
        related=rel,
    )


def render_rows(items):
    """index.html 아카이브 표에 미리 넣을 행 (JS가 불러오면 교체됨)."""
    e = lambda s: escape(str(s), quote=True)
    rows = []
    for it in items[:PRERENDER_ROWS]:
        rows.append(
            f'<tr class="main-row"><td class="col-type"><span class="badge badge-{e(it["type"])}">{e(it["type"])}</span></td>'
            f'<td class="col-date">{e(it["date"])}</td><td class="col-brand">{e(it["brand"])}</td>'
            f'<td class="col-product"><a href="n/{e(it["id"])}.html">{e(it.get("productName") or it["brand"])}</a></td>'
            f'<td class="col-title">{e(clip(it["summary"], 120))}</td><td class="col-toggle"></td></tr>')
    return "\n".join(rows)


def render_sitemap(items):
    latest = max((i["pub"] for i in items), default="")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           f"  <url><loc>{SITE_URL}/</loc><lastmod>{latest}</lastmod></url>"]
    out += [f"  <url><loc>{escape(page_url(i))}</loc><lastmod>{i['pub']}</lastmod></url>" for i in items]
    out += ["</urlset>", ""]
    return "\n".join(out)


def write_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def build_pages(root, items, pub):
    """items: news.json 전체, pub: 항목 → 게시일(미래 날짜는 오늘로). 바뀐 파일 수를 돌려줌."""
    items = [dict(i, pub=pub(i)) for i in visible(items)]
    changed = 0
    ndir = root / "n"
    ndir.mkdir(exist_ok=True)
    keep = set()
    for it in items:
        related = [r for r in items if r["brand"] == it["brand"] and r["id"] != it["id"]][:5]
        name = f"{it['id']}.html"
        keep.add(name)
        changed += write_if_changed(ndir / name, render_page(it, related))
    for old in ndir.glob("*.html"):  # 숨김 처리·삭제된 소식의 페이지 정리
        if old.name not in keep:
            old.unlink()
            changed += 1
    changed += write_if_changed(root / "sitemap.xml", render_sitemap(items))

    index = root / "index.html"
    html = index.read_text(encoding="utf-8")
    a, b = html.find(START), html.find(END)
    if a != -1 and b > a:
        new = html[: a + len(START)] + "\n" + render_rows(items) + "\n" + html[b:]

        # COUPANG PICKS 삽입 로직
        cp_path = root / "coupang_picks.html"
        if cp_path.exists():
            cp_html = cp_path.read_text(encoding="utf-8")
            cp_start = "<!-- COUPANG_PICKS:START -->"
            cp_end = "<!-- COUPANG_PICKS:END -->"
            a_cp = new.find(cp_start)
            b_cp = new.find(cp_end)
            if a_cp != -1 and b_cp > a_cp:
                new = new[: a_cp + len(cp_start)] + "\n" + cp_html + "\n" + new[b_cp:]

        changed += write_if_changed(index, new)
    return changed
