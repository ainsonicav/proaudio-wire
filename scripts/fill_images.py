#!/usr/bin/env python3
"""사진(imageUrl)이 없는 소식에 썸네일을 채웁니다. GitHub Actions에서 실행됩니다.

순서 (앞 단계에서 찾으면 멈춤):
  1) 원문 페이지의 대표 이미지(og:image / twitter:image)
  2) 원문 사이트가 자동 접속을 막으면 → 페이지 읽기 서비스(r.jina.ai)를 거쳐 다시 시도
  3) 대표 이미지 표시가 없으면 → 본문 안의 큰 사진
  4) 그래도 없으면 → "브랜드 + 제품명"으로 이미지 검색
       - Google (저장소 Secret GOOGLE_API_KEY, GOOGLE_CSE_ID가 있을 때)
       - 없거나 실패하면 DuckDuckGo → Bing 이미지 검색 (키 필요 없음)
       - 제목·주소에 브랜드명이 들어간 결과만 씀
  5) 모두 실패하면 사이트가 브랜드명 디자인 카드를 보여줌 (다음 실행 때 다시 시도)

찾은 이미지는 wsrv.nl 이미지 중계 주소로 저장하고, 저장 전에 실제로 열리는지 확인합니다.
imageSource: "original"(원문 사진) / "search"(검색으로 찾은 관련 이미지)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
RETRY_DAYS = 3
MAX_PER_RUN = 120
META_KEYS = ["og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src"]
BAD_HINTS = ("logo", "favicon", "default-og", "og-default", "placeholder", "blank.", "sprite",
             "icon", "avatar", "banner-ad", "1x1", "pixel", ".svg", "gravatar", "/flags/", "flag_",
             "localization", "store_switcher", "submenu", "/menu", "language", "country")
# 검색 결과에서 제외할 사이트 (무료 사진·배경화면·핀 모음 등 제품과 무관한 이미지가 많음)
BAD_SITES = ("pexels.com", "unsplash.com", "pixabay.com", "wallpaper", "shutterstock", "istockphoto",
             "gettyimages", "pinterest", "pinimg.com", "freepik", "dreamstime", "123rf", "alamy",
             "depositphotos", "vecteezy", "clipart", "wikimedia.org/wikipedia/commons/thumb")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
GOOGLE_CX = os.environ.get("GOOGLE_CSE_ID", "").strip()
stats = {"original": 0, "reader": 0, "body": 0, "google": 0, "duckduckgo": 0, "bing": 0, "none": 0}


# ---------- 공통 ----------
def http_get(url, headers=None, limit=2_000_000, timeout=20):
    h = {"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        charset = r.headers.get_content_charset() or "utf-8"
        raw = r.read(limit)
        return r.geturl(), ctype, raw, charset


def get_text(url, headers=None):
    final, ctype, raw, charset = http_get(url, headers)
    return final, ctype, raw.decode(charset, errors="replace")


def bad_image(u):
    lu = u.lower()
    return (not lu.startswith("http")) or any(h in lu for h in BAD_HINTS)


def proxied(img):
    return "https://wsrv.nl/?url=" + urllib.parse.quote(img, safe="") + "&w=640&default=1"


def image_works(img):
    """중계 서비스를 거쳐 실제 이미지가 열리는지 확인 (사이트에서 보이는 그대로)."""
    test = "https://wsrv.nl/?url=" + urllib.parse.quote(img, safe="") + "&w=64"
    try:
        _, ctype, raw, _ = http_get(test, limit=300_000, timeout=25)
        return ctype.startswith("image/") and len(raw) > 300
    except Exception:  # noqa: BLE001
        return False


# ---------- 1~3단계: 원문 ----------
class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.imgs, self.image_src = {}, [], None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            if key in META_KEYS and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "link" and a.get("rel", "").lower() == "image_src" and a.get("href"):
            self.image_src = a["href"].strip()
        elif tag == "img" and len(self.imgs) < 80:
            src = a.get("data-src") or a.get("data-lazy-src") or a.get("src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[-1].strip().split(" ")[0]
            try:
                w = int(re.sub(r"\D", "", a.get("width", "")) or 0)
            except ValueError:
                w = 0
            if src and not src.startswith("data:"):
                self.imgs.append((src.strip(), w, (a.get("alt") or a.get("title") or "").strip()))


def page_url(link):
    u = urllib.parse.urlparse(link)
    if u.netloc.lower() in ("blog.naver.com", "www.blog.naver.com"):
        q = urllib.parse.parse_qs(u.query)
        if "blogId" in q and "logNo" in q:
            return f"https://m.blog.naver.com/{q['blogId'][0]}/{q['logNo'][0]}"
        return "https://m.blog.naver.com" + u.path
    return link


def youtube_thumb(link):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", link)
    return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg" if m else None


def images_from_html(base, html, it):
    """(대표 이미지 후보들, 본문 사진 후보들). 본문 사진은 파일명·설명에 브랜드/제품명이 있는 것만."""
    p = PageParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    meta = [urllib.parse.urljoin(base, p.meta[k]) for k in META_KEYS if k in p.meta]
    if p.image_src:
        meta.append(urllib.parse.urljoin(base, p.image_src))
    body = []
    toks = product_tokens(it) + brand_tokens(first_brand(it))
    for src, w, alt in p.imgs:
        full = urllib.parse.urljoin(base, src)
        if bad_image(full) or (w and w < 250):
            continue
        hay = (urllib.parse.unquote(full) + " " + alt).lower().replace("_", " ").replace("-", " ")
        if any(t in hay for t in toks):
            body.append(full)
    return [m for m in meta if not bad_image(m)], body


def from_original(it):
    link = it["link"]
    yt = youtube_thumb(link)
    if yt:
        return [("original", yt)]
    url = page_url(link)
    cands = []
    html, base = None, url
    try:
        base, ctype, html = get_text(url)
        if "html" not in ctype and "<html" not in html[:3000].lower():
            html = None
    except Exception:  # noqa: BLE001
        html = None
    if html is None:
        # 2) 자동 접속 차단 시: 페이지 읽기 서비스로 우회
        try:
            _, _, html = get_text("https://r.jina.ai/" + url, {"X-Return-Format": "html"})
            base = url
            meta, body = images_from_html(base, html, it)
            return [("reader", m) for m in meta] + [("body", b) for b in body[:3]]
        except Exception:  # noqa: BLE001
            return []
    meta, body = images_from_html(base, html, it)
    cands += [("original", m) for m in meta]
    cands += [("body", b) for b in body[:3]]
    return cands


# ---------- 4단계: 이미지 검색 ----------
def first_brand(it):
    return re.split(r"[;,]", it.get("brand") or "")[0].strip()


def product_tokens(it):
    brand = first_brand(it).lower()
    prod = re.split(r"[,;/(]| 및 | and ", it.get("productName") or "")[0].lower()
    words = re.sub(r"[^0-9a-z가-힣ø.]+", " ", prod.replace(brand, " ")).split()
    stop = {"the", "for", "new", "series", "update", "firmware", "version", "plugin", "plugins",
            "공동", "발표", "업데이트", "신제품", "시리즈", "패키지", "종"}
    return [w.strip(".") for w in words if len(w.strip(".")) >= 3 and w not in stop and not re.fullmatch(r"v?[\d.]+", w)]


def search_query(it):
    brand = first_brand(it)
    prod = re.split(r"[,;/(]| 및 | and ", it.get("productName") or "")[0].strip()
    if prod.lower().startswith(brand.lower()):
        prod = prod[len(brand):].strip()
    return f"{brand} {prod}".strip(), brand


def brand_tokens(brand):
    b = re.sub(r"[^0-9a-z가-힣ø]+", " ", brand.lower()).split()
    return [t for t in b if len(t) >= 2] or [brand.lower()]


RELEVANCE = {"toks": []}


def relevant(brand, *texts):
    """브랜드명이 있어야 하고, 제품명 단어가 있으면 그중 하나도 있어야 함. 사진 모음 사이트는 제외."""
    blob = urllib.parse.unquote(" ".join(texts)).lower().replace("_", " ").replace("-", " ")
    if any(b in blob for b in BAD_SITES):
        return False
    btoks = brand_tokens(brand)
    if not (any(t in blob for t in btoks) or brand.lower().replace("ø", "o") in blob):
        return False
    ptoks = RELEVANCE["toks"]
    return not ptoks or any(t in blob for t in ptoks)


def search_google(q, brand):
    if not (GOOGLE_KEY and GOOGLE_CX):
        return []
    url = ("https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(
        {"key": GOOGLE_KEY, "cx": GOOGLE_CX, "q": q, "searchType": "image", "num": 8, "safe": "active"}))
    _, _, txt = get_text(url)
    out = []
    for r in json.loads(txt).get("items", []):
        ctx = (r.get("image") or {}).get("contextLink", "")
        if relevant(brand, r.get("title", ""), r.get("link", ""), ctx):
            out.append(("google", r["link"]))
            thumb = (r.get("image") or {}).get("thumbnailLink")
            if thumb:
                out.append(("google", thumb))
    return out


def search_ddg(q, brand):
    _, _, html = get_text("https://duckduckgo.com/?" + urllib.parse.urlencode({"q": q, "iax": "images", "ia": "images"}))
    m = re.search(r"vqd=[\"']?([\d-]+)", html)
    if not m:
        return []
    api = "https://duckduckgo.com/i.js?" + urllib.parse.urlencode(
        {"l": "wt-wt", "o": "json", "q": q, "vqd": m.group(1), "f": ",,,,,", "p": "1"})
    _, _, txt = get_text(api, {"Referer": "https://duckduckgo.com/", "Accept": "application/json"})
    out = []
    for r in json.loads(txt).get("results", [])[:15]:
        if (r.get("width") or 999) < 250:
            continue
        if relevant(brand, r.get("title", ""), r.get("url", ""), r.get("image", "")):
            out.append(("duckduckgo", r["image"]))
            if r.get("thumbnail"):
                out.append(("duckduckgo", r["thumbnail"]))
    return out


def search_bing(q, brand):
    _, _, html = get_text("https://www.bing.com/images/search?" + urllib.parse.urlencode({"q": q, "form": "HDRSC2"}))
    out = []
    for m in re.finditer(r'class="iusc"[^>]*?\sm="([^"]+)"', html):
        try:
            d = json.loads(unescape(m.group(1)))
        except ValueError:
            continue
        if relevant(brand, d.get("t", ""), d.get("purl", ""), d.get("murl", "")):
            out.append(("bing", d["murl"]))
            if d.get("turl"):
                out.append(("bing", d["turl"]))
        if len(out) >= 12:
            break
    return out


def from_search(it):
    q, brand = search_query(it)
    if not brand:
        return []
    # 4-a) 브랜드+제품명으로 검색, 제품명 단어까지 맞는 결과만
    # 4-b) 없으면 "브랜드 audio"로 검색해 그 브랜드의 대표 제품 사진 (맥락상 관련 이미지)
    for query, toks in ((q, product_tokens(it)), (f"{brand} audio", [])):
        RELEVANCE["toks"] = toks
        for fn in (search_google, search_ddg, search_bing):
            try:
                c = [x for x in fn(query, brand) if not bad_image(x[1]) or "bing.net" in x[1] or "ytimg" in x[1]]
            except Exception as e:  # noqa: BLE001
                print(f"    {fn.__name__} 실패: {type(e).__name__}: {str(e)[:60]}")
                c = []
            if c:
                yield from c
            time.sleep(1)


# ---------- 실행 ----------
USED = {}  # 이미지 주소 → 이미 쓰인 소식의 제품명 (다른 제품에 같은 사진이면 사이트 공통 이미지로 보고 제외)


def pick(cands, it):
    seen = set()
    key = (it.get("productName") or it.get("id")).lower()
    for src, img in cands:
        if img in seen:
            continue
        seen.add(img)
        if img in USED and USED[img] != key:
            continue
        if image_works(img):
            USED[img] = key
            return src, img
    return None, None


def main():
    items = json.loads(NEWS.read_text(encoding="utf-8"))
    today = date.today()
    for it in items:
        if it.get("imageUrl"):
            m = re.search(r"url=([^&]+)", it["imageUrl"])
            USED[urllib.parse.unquote(m.group(1)) if m else it["imageUrl"]] = (it.get("productName") or it["id"]).lower()
    todo = []
    for it in items:
        it.pop("imageChecked", None)  # 옛 버전 표시 정리
        if it.get("imageUrl") or it.get("status") == "hidden" or not str(it.get("link", "")).startswith("http"):
            continue
        tried = it.get("imageTried")
        if tried:
            try:
                if date.fromisoformat(tried) > today - timedelta(days=RETRY_DAYS):
                    continue
            except ValueError:
                pass
        todo.append(it)

    changed = False
    for it in todo[:MAX_PER_RUN]:
        src, img = pick(from_original(it), it)
        if not img:
            src, img = pick(from_search(it), it)
        if img:
            it["imageUrl"] = proxied(img)
            it["imageSource"] = "search" if src in ("google", "duckduckgo", "bing") else ("body" if src == "body" else "original")
            it.pop("imageTried", None)
            stats[src] += 1
            print(f"  {it['id']}: [{src}] {img[:100]}")
        else:
            it["imageTried"] = today.isoformat()
            stats["none"] += 1
            print(f"  {it['id']}: 못 찾음")
        changed = True

    # 옛 imageChecked 표시만 지운 경우도 저장
    text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if changed or text != NEWS.read_text(encoding="utf-8"):
        NEWS.write_text(text, encoding="utf-8")
    found = sum(v for k, v in stats.items() if k != "none")
    detail = ", ".join(f"{k} {v}" for k, v in stats.items() if v)
    print(f"사진 추가 {found}건, 못 찾음 {stats['none']}건 ({detail})")
    print(f"::notice title=사진 채우기::사진 추가 {found}건, 못 찾음 {stats['none']}건 ({detail or '대상 없음'})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
