#!/usr/bin/env python3
"""사진(imageUrl)이 없는 소식에 썸네일을 채웁니다. GitHub Actions에서 실행됩니다.

순서 (앞 단계에서 찾으면 멈춤):
  1) 원문 페이지의 대표 이미지(og:image / twitter:image) — 단, 이 소식의 제품명 단어가
     이미지 주소 안에 실제로 있는 것만 씁니다(아래 "대표 이미지도 근거 필요" 참고).
  2) 원문 사이트가 자동 접속을 막으면 → 페이지 읽기 서비스(r.jina.ai)를 거쳐 다시 시도
  3) 대표 이미지 표시가 없으면 → 본문 안의 큰 사진(역시 제품명 단어가 있는 것만)
  4) 그래도 없으면 → "브랜드 + 제품명"으로 이미지 검색
       - Google 이미지 검색 (SerpApi 경유, 저장소 Secret SERPAPI_KEY가 있을 때)
       - 없거나 실패하면 DuckDuckGo → Bing 이미지 검색 (키 필요 없음)
       - 제목·주소에 브랜드명 + 제품명 단어가 모두 들어간 결과만 씀
  5) 모두 실패하면 사이트가 브랜드명 디자인 카드를 보여줌 (다음 실행 때 다시 시도)

대표 이미지도 근거 필요: 예전에는 원문 기사의 og:image를 "기사 자체가 근거"라고 보고
무조건 받아들였습니다. 하지만 여러 제품을 묶어 소개하는 기사나 사이트 공통 로고/배너가
og:image로 잡히면 엉뚱한 제품 사진이 붙을 수 있어, 지금은 og:image도 이미지 주소 안에
이 소식의 제품명 단어가 있어야만 채택합니다(유튜브 영상 썸네일은 그 기사가 직접 담고 있는
고유 영상 ID에서 나온 것이라 예외). 제품명을 모르면(productName 없음) og:image도,
검색도 전혀 시도하지 않습니다 — "근거 없으면 사진 없음"이 기본 정책입니다.

시간 예산(FILL_IMAGES_TIME_BUDGET_SEC)은 전체 실행뿐 아니라 각 HTTP 요청 하나하나에도
전달됩니다 — 남은 예산이 요청의 기본 타임아웃보다 적으면 그 적은 쪽을 씁니다. 그래서 전체
실행 시간은 예산 + 아주 짧은 여유(마지막 한 요청의 남은 시간만큼)로 바운드됩니다. 예산이
떨어진 "도중에" 처리가 끊긴 항목은 "시도했지만 못 찾음"으로 기록하지 않습니다(imageTried
표시를 남기지 않음) — 그래야 다음 실행에서 재시도 대기(RETRY_DAYS) 없이 바로 다시 시도합니다.

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
# 한 번 실행에 쓰는 전체 시간 예산(초). 이를 넘기면 남은 항목은 건너뛰고 지금까지 찾은 것만
# 저장합니다(news-write concurrency 그룹을 길게 점유해 글 게시를 막지 않기 위함). 이 값은
# main()이 시작할 때 DEADLINE으로 고정되고, 모든 개별 HTTP 요청의 타임아웃도 이 안에서
# "남은 시간"으로 깎여 전체 실행이 예산 + 짧은 여유 안에서 끝나도록 합니다.
TIME_BUDGET_SEC = int(os.environ.get("FILL_IMAGES_TIME_BUDGET_SEC", "1200") or "1200")
META_KEYS = ["og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src"]
BAD_HINTS = ("logo", "favicon", "default-og", "og-default", "placeholder", "blank.", "sprite",
             "icon", "avatar", "banner-ad", "1x1", "pixel", ".svg", "gravatar", "/flags/", "flag_",
             "localization", "store_switcher", "submenu", "/menu", "language", "country")
# 검색 결과에서 제외할 사이트 (무료 사진·배경화면·핀 모음 등 제품과 무관한 이미지가 많음)
BAD_SITES = ("pexels.com", "unsplash.com", "pixabay.com", "wallpaper", "shutterstock", "istockphoto",
             "gettyimages", "pinterest", "pinimg.com", "freepik", "dreamstime", "123rf", "alamy",
             "depositphotos", "vecteezy", "clipart", "wikimedia.org/wikipedia/commons/thumb", "wallup",
             "facts.net", "srcdn.com", "wallhaven", "hdqwalls", "nature", "travel",
             "books", "novel", "audiobook", "kindle", "goodreads", "amazon.com/images/i/")
# 브랜드명만으로 찾을 때는 음향 관련 단어가 함께 있어야 함
AUDIO_WORDS = ("audio", "sound", "mic", "speaker", "mixer", "console", "plugin", "plug-in", "headphone",
               "interface", "studio", "monitor", "amplifier", "amp", "wireless", "loudspeaker", "daw",
               "synth", "recording", "broadcast", "pro audio", "음향", "스피커", "마이크")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()
SEARCH_LOG = {}  # 검색 엔진별: 결과 있음 / 관련 결과 없음 / 오류
stats = {"original": 0, "reader": 0, "body": 0, "google": 0, "duckduckgo": 0, "bing": 0, "none": 0}


class BudgetExceeded(Exception):
    """시간 예산이 소진돼 더 이상 네트워크 요청을 시작할 수 없을 때 발생.
    "시도했지만 못 찾음"과 구분하기 위해 일반 except Exception에 묻히지 않고 항상
    main()까지 그대로 전파되어야 함 — 각 try/except 블록에서 명시적으로 재던짐."""


# ---------- 공통 ----------
DEADLINE = None  # main()에서 time.monotonic() + TIME_BUDGET_SEC로 설정


def remaining_budget():
    """남은 시간 예산(초). DEADLINE이 설정 안 돼 있으면(단독 함수 테스트 등) 무제한으로 취급."""
    if DEADLINE is None:
        return float("inf")
    return DEADLINE - time.monotonic()


def http_get(url, headers=None, limit=2_000_000, timeout=20):
    budget = remaining_budget()
    if budget <= 0:
        raise BudgetExceeded(f"시간 예산 소진 (요청 전 중단): {url[:80]}")
    eff_timeout = min(timeout, budget)
    h = {"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=eff_timeout) as r:
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
    except BudgetExceeded:
        raise
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


def _url_matches_tokens(url, ptoks):
    """이미지 주소의 경로·쿼리 부분에 제품명 단어가 실제로 들어 있는지 확인(도메인은 제외)."""
    u = urllib.parse.urlparse(url)
    hay = urllib.parse.unquote(u.path + " " + u.query).lower().replace("_", " ").replace("-", " ")
    return any(t in hay for t in ptoks)


def images_from_html(base, html, it):
    """(대표 이미지 후보들, 본문 사진 후보들). 대표 이미지(og:image 등)와 본문 사진 모두
    이 소식의 제품명 단어가 이미지 주소/설명에 실제로 있는 것만 채택합니다 — og:image라고
    무조건 신뢰하지 않습니다(여러 제품을 묶은 기사나 사이트 공통 배너가 og:image로 잡히면
    엉뚱한 제품 사진이 붙을 수 있음). 제품명을 모르면(ptoks 없음) 대표 이미지도 채택하지
    않습니다 — "근거 없으면 사진 없음" 정책을 og:image에도 동일하게 적용."""
    p = PageParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    meta = [urllib.parse.urljoin(base, p.meta[k]) for k in META_KEYS if k in p.meta]
    if p.image_src:
        meta.append(urllib.parse.urljoin(base, p.image_src))
    meta = [m for m in meta if not bad_image(m)]

    ptoks = product_tokens(it)
    if ptoks:
        meta = [m for m in meta if _url_matches_tokens(m, ptoks)]
    else:
        meta = []  # 제품명 단서가 전혀 없으면 og:image도 신뢰하지 않음(unknown = no image)

    body = []
    for src, w, alt in p.imgs:
        full = urllib.parse.urljoin(base, src)
        if bad_image(full) or (w and w < 250):
            continue
        u = urllib.parse.urlparse(full)  # 도메인은 빼고 파일 경로·설명만 봄
        hay = (urllib.parse.unquote(u.path + " " + u.query) + " " + alt).lower().replace("_", " ").replace("-", " ")
        if ptoks and any(t in hay for t in ptoks):
            body.append(full)
    return meta, body


def from_original(it):
    link = it["link"]
    yt = youtube_thumb(link)
    if yt:
        # 유튜브 썸네일은 이 기사가 직접 담고 있는 고유 영상 ID에서 뽑은 것이라
        # 다른 소식과 섞일 위험이 없어 제품명 토큰 검사 없이도 신뢰할 수 있는 예외입니다.
        return [("original", yt)]
    url = page_url(link)
    cands = []
    html, base = None, url
    try:
        base, ctype, html = get_text(url)
        if "html" not in ctype and "<html" not in html[:3000].lower():
            html = None
    except BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001
        html = None
    if html is None:
        # 2) 자동 접속 차단 시: 페이지 읽기 서비스로 우회
        try:
            _, _, html = get_text("https://r.jina.ai/" + url, {"X-Return-Format": "html"})
            base = url
            meta, body = images_from_html(base, html, it)
            return [("reader", m) for m in meta] + [("body", b) for b in body[:3]]
        except BudgetExceeded:
            raise
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
            "software", "release", "system", "license", "공동", "발표", "업데이트", "신제품", "시리즈",
            "패키지", "플러그인", "인터페이스", "펌웨어", "소프트웨어"}
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
    """브랜드명이 있어야 하고, 제품명 단어 중 하나도 반드시 있어야 함(근거 없는 브랜드 대표 사진으로
    때우는 것을 막기 위해 제품명 단어가 없으면 검색을 아예 시도하지 않음 — from_search 참고). 사진 모음 사이트는 제외."""
    blob = urllib.parse.unquote(" ".join(texts)).lower().replace("_", " ").replace("-", " ")
    if any(b in blob for b in BAD_SITES):
        return False
    btoks = brand_tokens(brand)
    if not (all(t in blob for t in btoks) or brand.lower().replace("ø", "o") in blob):
        return False
    ptoks = RELEVANCE["toks"]
    if not ptoks:
        return False
    return any(t in blob for t in ptoks)


SERP_BUDGET = {"left": 60}  # 한 번 실행에 쓰는 검색 횟수 상한 (무료 250회/월 안에서)


def search_google(q, brand):
    """Google 이미지 검색 결과 (SerpApi 경유). 저장소 Secret SERPAPI_KEY 필요."""
    if not SERPAPI_KEY or SERP_BUDGET["left"] <= 0:
        return []
    SERP_BUDGET["left"] -= 1
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(
        {"engine": "google_images", "q": q, "api_key": SERPAPI_KEY, "hl": "en", "gl": "us", "safe": "active"})
    _, _, txt = get_text(url)
    data = json.loads(txt)
    if data.get("error"):
        raise RuntimeError(data["error"][:80])
    out = []
    for r in data.get("images_results", [])[:20]:
        if (r.get("original_width") or 999) < 250:
            continue
        if relevant(brand, r.get("title", ""), r.get("link", ""), r.get("source", ""), r.get("original", "")):
            if r.get("original"):
                out.append(("google", r["original"]))
            if r.get("thumbnail"):
                out.append(("google", r["thumbnail"]))
    return out


def search_ddg(q, brand):
    _, _, html = get_text("https://duckduckgo.com/?" + urllib.parse.urlencode({"q": q, "iax": "images", "ia": "images"}))
    m = re.search(r"vqd=[\"']?([\d-]+)", html)
    if not m:
        raise RuntimeError(f"vqd 없음 (html {len(html)}자)")
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
    raw = re.findall(r'class="iusc"[^>]*?\sm="([^"]+)"', html)
    SEARCH_LOG.setdefault("bing_raw", {"hit": 0, "empty": 0, "err": 0, "last": ""})["hit" if raw else "empty"] += 1
    if not raw:
        SEARCH_LOG["bing_raw"]["last"] = f"html {len(html)}자 murl {html.count('murl')}"
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
    """제품명을 구체적으로 알 수 없으면(product_tokens가 비어있으면) 검색을 아예 하지 않습니다.
    예전에는 "브랜드 audio" 등으로 넘어가서 근거 없는 브랜드 대표 사진을 붙이는 폴백이 있었지만,
    기사/제품과 무관한 사진이 붙을 위험이 커서 제거했습니다 — 근거 없으면 사진 없음(no image)이 정책."""
    q, brand = search_query(it)
    toks = product_tokens(it)
    if not brand or not toks:
        return
    RELEVANCE["toks"] = toks
    for fn in (search_google, search_ddg, search_bing):
        if remaining_budget() <= 0:
            raise BudgetExceeded("시간 예산 소진 (검색 엔진 호출 전 중단)")
        log = SEARCH_LOG.setdefault(fn.__name__[7:], {"hit": 0, "empty": 0, "err": 0, "last": ""})
        try:
            c = [x for x in fn(q, brand) if not bad_image(x[1]) or "bing.net" in x[1] or "ytimg" in x[1]]
            log["hit" if c else "empty"] += 1
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"    {fn.__name__} 실패: {type(e).__name__}: {str(e)[:60]}")
            log["err"] += 1
            log["last"] = f"{type(e).__name__}: {str(e)[:50]}"
            c = []
        if c:
            yield from c
        if remaining_budget() <= 0:
            raise BudgetExceeded("시간 예산 소진 (검색 엔진 사이 대기 전 중단)")
        time.sleep(min(1, max(0, remaining_budget())))


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
    global DEADLINE
    items = json.loads(NEWS.read_text(encoding="utf-8"))
    today = date.today()
    for it in items:
        if it.get("imageUrl"):
            m = re.search(r"url=([^&]+)", it["imageUrl"])
            USED[urllib.parse.unquote(m.group(1)) if m else it["imageUrl"]] = (it.get("productName") or it["id"]).lower()
    todo = []
    for it in items:
        it.pop("imageChecked", None)  # 옛 버전 표시 정리
        # imageSource가 "manual"이면 사람이 직접 확인해 넣은 사진이므로 자동화가 절대 건드리지 않음.
        if it.get("imageUrl") or it.get("imageSource") == "manual" or it.get("status") == "hidden" \
                or not str(it.get("link", "")).startswith("http"):
            continue
        tried = it.get("imageTried") or ""
        # 검색 키 없이 시도했던 항목은 키가 생기면 바로 다시 시도
        if tried and not (SERPAPI_KEY and not tried.endswith(":g")):
            try:
                if date.fromisoformat(tried[:10]) > today - timedelta(days=RETRY_DAYS):
                    continue
            except ValueError:
                pass
        todo.append(it)

    DEADLINE = time.monotonic() + TIME_BUDGET_SEC
    changed = False
    processed = 0
    budget_hit = False
    for it in todo[:MAX_PER_RUN]:
        if remaining_budget() <= 0:
            budget_hit = True
            break
        try:
            src, img = pick(from_original(it), it)
            if not img:
                src, img = pick(from_search(it), it)
        except BudgetExceeded:
            # 처리 도중 예산이 떨어진 항목은 "시도했지만 못 찾음"으로 기록하지 않습니다
            # (imageTried를 남기지 않음) — 다음 실행에서 RETRY_DAYS 대기 없이 바로 재시도.
            budget_hit = True
            break
        if img:
            it["imageUrl"] = proxied(img)
            it["imageSource"] = "search" if src in ("google", "duckduckgo", "bing") else ("body" if src == "body" else "original")
            it.pop("imageTried", None)
            stats[src] += 1
            print(f"  {it['id']}: [{src}] {img[:100]}")
        else:
            it["imageTried"] = today.isoformat() + (":g" if SERPAPI_KEY else "")
            stats["none"] += 1
            print(f"  {it['id']}: 못 찾음 (근거 없는 브랜드 대표 사진은 쓰지 않음)")
        changed = True
        processed += 1

    remaining = len(todo) - processed
    if budget_hit and remaining > 0:
        print(f"  시간 예산({TIME_BUDGET_SEC}초) 초과로 중단, 남은 {remaining}건은 다음 실행에서 계속 (재시도 대기 없이 바로)")

    # 옛 imageChecked 표시만 지운 경우도 저장
    text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    if changed or text != NEWS.read_text(encoding="utf-8"):
        NEWS.write_text(text, encoding="utf-8")
    found = sum(v for k, v in stats.items() if k != "none")
    detail = ", ".join(f"{k} {v}" for k, v in stats.items() if v)
    budget_note = f", 시간예산 초과로 {remaining}건 이월" if budget_hit and remaining > 0 else ""
    print(f"사진 추가 {found}건, 못 찾음 {stats['none']}건, 처리 {processed}/{len(todo)}건 ({detail}){budget_note}")
    if SEARCH_LOG:
        print("::notice title=이미지 검색 상태::" + " | ".join(
            f"{k} 결과 {v['hit']} · 없음 {v['empty']} · 오류 {v['err']} {v['last']}" for k, v in SEARCH_LOG.items()), flush=True)
    print(f"::notice title=사진 채우기::사진 추가 {found}건, 못 찾음 {stats['none']}건 ({detail or '대상 없음'}){budget_note}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
