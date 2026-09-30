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
SITE_NAME = "PRO AUDIO WIRE"
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
<meta name="twitter:card" content="{card}">
<script type="application/ld+json">{ld}</script>
<style>
body{{margin:0;background:#f8fafc;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;line-height:1.7;word-break:keep-all;overflow-wrap:anywhere}}
header{{background:#fff;border-bottom:1px solid #e2e8f0;padding:.8rem 1rem}}
header a{{color:#0f172a;text-decoration:none;font-weight:800}}
header span{{background:#e11d48;color:#fff;font-size:.7rem;padding:.15rem .45rem;border-radius:4px;margin-right:.4rem}}
main{{max-width:760px;margin:0 auto;padding:1.5rem 1rem 3rem}}
.meta{{font-size:.85rem;color:#64748b;margin:0}}
.badge{{display:inline-block;background:#ffe4e6;color:#be123c;font-weight:700;font-size:.75rem;padding:.1rem .5rem;border-radius:4px;margin-right:.4rem}}
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
<header><a href="/"><span>PRO AUDIO</span>WIRE</a></header>
<main>
<article>
<p class="meta"><span class="badge">{type}</span>{category} · {brand_line} · <time datetime="{date}">{date}</time></p>
<h1>{h1}</h1>
{img}<p class="summary">{summary}</p>
{evidence}<p><a class="btn" href="{link}" target="_blank" rel="noopener noreferrer">원문 출처 보기 ↗</a><a class="btn sub" href="/?n={id}">전체 소식 목록</a></p>
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
        og_image=f'<meta property="og:image" content="{e(img)}">\n' if img else "",
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
