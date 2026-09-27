#!/usr/bin/env python3
"""사진(imageUrl)이 없는 소식의 원문을 열어 대표 이미지를 찾아 채웁니다.

GitHub Actions에서 실행됩니다 (원문 사이트 접속이 필요해서).
- 원문 페이지의 og:image / twitter:image 를 찾습니다.
- 네이버 블로그는 모바일 주소(m.blog.naver.com)로, 유튜브는 영상 썸네일로 처리합니다.
- 찾은 이미지는 wsrv.nl 이미지 중계 주소로 저장합니다
  (일부 사이트가 다른 사이트에서 사진을 불러오는 것을 막기 때문).
- 못 찾은 항목은 imageChecked 날짜를 남겨 매번 다시 시도하지 않습니다(14일 뒤 재시도).

사용법: python3 scripts/fill_images.py   (바뀐 게 있으면 news.json 저장)
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
RETRY_DAYS = 14
MAX_PER_RUN = 150
META_KEYS = ["og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src"]
# 사이트 공통 로고·기본 이미지로 보이는 것은 건너뜀
BAD_HINTS = ("logo", "favicon", "default-og", "og-default", "placeholder", "blank.")


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.image_src = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            if key in META_KEYS and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "link" and a.get("rel", "").lower() == "image_src" and a.get("href"):
            self.image_src = a["href"].strip()


def fetch(url, limit=1_500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        ctype = r.headers.get("Content-Type", "")
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), ctype, r.read(limit).decode(charset, errors="replace")


def page_url(link):
    """원문 주소를 대표 이미지를 읽기 쉬운 주소로 바꿈."""
    u = urllib.parse.urlparse(link)
    host = u.netloc.lower()
    if host in ("blog.naver.com", "www.blog.naver.com"):
        q = urllib.parse.parse_qs(u.query)
        if "blogId" in q and "logNo" in q:
            return f"https://m.blog.naver.com/{q['blogId'][0]}/{q['logNo'][0]}"
        return "https://m.blog.naver.com" + u.path
    return link


def youtube_thumb(link):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", link)
    return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg" if m else None


def find_image(link):
    yt = youtube_thumb(link)
    if yt:
        return yt
    final, ctype, html = fetch(page_url(link))
    if "html" not in ctype and "<html" not in html[:2000].lower():
        return None
    p = MetaParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - 깨진 HTML도 앞부분만으로 충분
        pass
    for k in META_KEYS:
        if k in p.meta:
            img = urllib.parse.urljoin(final, p.meta[k])
            if img.startswith("http") and not any(h in img.lower() for h in BAD_HINTS):
                return img
    if p.image_src:
        return urllib.parse.urljoin(final, p.image_src)
    return None


def proxied(img):
    return "https://wsrv.nl/?url=" + urllib.parse.quote(img, safe="") + "&w=640&default=1"


def main():
    items = json.loads(NEWS.read_text(encoding="utf-8"))
    today = date.today()
    todo = []
    for it in items:
        if it.get("imageUrl") or it.get("status") == "hidden" or not str(it.get("link", "")).startswith("http"):
            continue
        checked = it.get("imageChecked")
        if checked:
            try:
                if date.fromisoformat(checked) > today - timedelta(days=RETRY_DAYS):
                    continue
            except ValueError:
                pass
        todo.append(it)

    found = missed = 0
    for it in todo[:MAX_PER_RUN]:
        try:
            img = find_image(it["link"])
        except Exception as e:  # noqa: BLE001
            img = None
            print(f"  {it['id']}: 열기 실패 ({type(e).__name__}: {str(e)[:80]})")
        if img:
            it["imageUrl"] = proxied(img)
            it.pop("imageChecked", None)
            found += 1
            print(f"  {it['id']}: 사진 찾음 {img[:90]}")
        else:
            it["imageChecked"] = today.isoformat()
            missed += 1

    if found or missed:
        NEWS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"확인 {found + missed}건: 사진 추가 {found}건, 못 찾음 {missed}건")
    print(f"::notice title=사진 채우기::사진 추가 {found}건, 못 찾음 {missed}건", flush=True)


if __name__ == "__main__":
    sys.exit(main())
