"""fill_images.py 테스트. 실제 네트워크 호출은 전혀 하지 않습니다 — HTML 파싱·관련성
판정 같은 순수 로직은 직접 호출하고, main()의 네트워크 의존 함수(from_original/from_search/
image_works)는 모두 monkeypatch로 가짜(fixture) 응답으로 바꿔치기합니다.

다루는 범위:
  - 기사와 무관한(og:image가 로고/배너인) 이미지, 브랜드만 일치하고 제품과 무관한 "오인식"
    이미지 거부 (근거 없는 브랜드 대표 사진 금지)
  - 제품명을 모르면 이미지 검색 자체를 시도하지 않음(unknown = no image)
  - 이미 사람이 확인한(imageSource: manual) 사진은 절대 덮어쓰지 않음
  - 시간 예산(TIME_BUDGET_SEC)을 넘기면 중단하고 처리한 만큼만 저장
"""
import json
import unittest
from pathlib import Path
from unittest import mock

import conftest_helper  # noqa: F401

import fill_images  # noqa: E402


def item(**over):
    base = {
        "id": "news-1",
        "link": "https://example.com/article",
        "brand": "ExampleBrand",
        "productName": "ExampleBrand X1 Mixer",
    }
    base.update(over)
    return base


class RelevanceTests(unittest.TestCase):
    def test_rejects_image_without_product_tokens_even_if_brand_matches(self):
        """브랜드명만 맞고 제품명 단서가 전혀 없는 "브랜드 대표 사진" 오인식을 막는지 확인."""
        fill_images.RELEVANCE["toks"] = []
        self.assertFalse(fill_images.relevant("ExampleBrand", "ExampleBrand official site banner"))

    def test_accepts_when_brand_and_product_token_both_present(self):
        fill_images.RELEVANCE["toks"] = ["mixer"]
        self.assertTrue(fill_images.relevant("ExampleBrand", "ExampleBrand X1 Mixer review photo"))

    def test_rejects_when_product_token_missing(self):
        fill_images.RELEVANCE["toks"] = ["mixer"]
        self.assertFalse(fill_images.relevant("ExampleBrand", "ExampleBrand headphones photo"))

    def test_rejects_bad_sites(self):
        fill_images.RELEVANCE["toks"] = ["mixer"]
        self.assertFalse(fill_images.relevant("ExampleBrand", "ExampleBrand mixer", "https://pinterest.com/pin/1"))


class FromSearchGatingTests(unittest.TestCase):
    def test_skips_search_entirely_without_product_tokens(self):
        """product_tokens가 비어 있으면(제품명을 구체적으로 모르면) 검색 함수들을
        호출조차 하지 않아야 함 — 호출되면 테스트가 실패하도록 함정을 심음."""
        def boom(*a, **k):
            raise AssertionError("검색 함수가 호출되면 안 됨 (근거 없는 폴백 금지)")

        orig = (fill_images.search_google, fill_images.search_ddg, fill_images.search_bing)
        fill_images.search_google = boom
        fill_images.search_ddg = boom
        fill_images.search_bing = boom
        try:
            it = item(productName="")  # 제품명 없음 -> product_tokens 비어있음
            result = list(fill_images.from_search(it))
            self.assertEqual(result, [])
        finally:
            fill_images.search_google, fill_images.search_ddg, fill_images.search_bing = orig


class ImagesFromHtmlTests(unittest.TestCase):
    def test_rejects_logo_og_image(self):
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/logo.png"></head><body></body></html>'
        it = item()
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(meta, [])  # logo 힌트로 걸러짐

    def test_accepts_article_specific_og_image(self):
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/photos/x1-mixer-hero.jpg"></head></html>'
        it = item()
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(meta, ["https://cdn.example.com/photos/x1-mixer-hero.jpg"])

    def test_rejects_generic_og_image_with_no_product_token(self):
        """이전에는 og:image를 기사 자체의 근거로 보고 무조건 신뢰했지만, 제품명 단서가
        전혀 없는 범용(사이트 공통) 카드는 logo/favicon 힐트가 없어도 거부되어야 함."""
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/assets/default-card.jpg"></head></html>'
        it = item()
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(meta, [])

    def test_rejects_og_image_belonging_to_different_model(self):
        """og:image가 이 소식과 다른 제품(다른 모델)을 가리키는 경우 거부 — 여러 제품을 묶은
        기사의 기본 카드가 엉둩한 제품 사진으로 붙는 것을 막기 위함."""
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/photos/y2-compressor-hero.jpg"></head></html>'
        it = item()  # productName: ExampleBrand X1 Mixer
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(meta, [])

    def test_og_image_rejected_when_product_name_unknown(self):
        """제품명을 모르면(productName 없음) og:image도 채택하지 않음 (unknown = no image)."""
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/photos/x1-mixer-hero.jpg"></head></html>'
        it = item(productName="")
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(meta, [])

    def test_youtube_thumbnail_exempt_from_product_token_check(self):
        """유튜브 영상 썸네일은 이 기사가 직접 담고 있는 고유 영상 ID에서 나온 것이라 예외."""
        it = item(link="https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(fill_images.youtube_thumb(it["link"]), "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg")

    def test_body_image_requires_product_token_match_no_brand_only_fallback(self):
        html = (
            '<html><body>'
            '<img src="https://cdn.example.com/img/sidebar-ad-banner.jpg" width="400">'
            '<img src="https://cdn.example.com/img/x1-mixer-detail.jpg" width="400" alt="X1 Mixer detail shot">'
            '</body></html>'
        )
        it = item()
        meta, body = fill_images.images_from_html("https://example.com/article", html, it)
        self.assertEqual(body, ["https://cdn.example.com/img/x1-mixer-detail.jpg"])


class ManualImageProtectionTests(unittest.TestCase):
    """main()의 todo 필터링 로직: imageUrl이 있거나 imageSource가 manual이면 절대 건드리지 않음."""

    def setUp(self):
        import time
        import uuid
        holder = Path(__file__).resolve().parent / ".tmp"
        holder.mkdir(exist_ok=True)
        self.news_path = holder / f"news-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}.json"
        self._orig_news = fill_images.NEWS
        self._orig_budget = fill_images.TIME_BUDGET_SEC

    def tearDown(self):
        fill_images.NEWS = self._orig_news
        fill_images.TIME_BUDGET_SEC = self._orig_budget
        if self.news_path.exists():
            self.news_path.unlink()

    def test_manual_and_existing_images_are_never_touched(self):
        items = [
            item(id="news-1", imageUrl="https://wsrv.nl/?url=manual.jpg", imageSource="manual"),
            item(id="news-2", imageUrl="https://wsrv.nl/?url=already-found.jpg", imageSource="original"),
        ]
        self.news_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        fill_images.NEWS = self.news_path

        def boom(*a, **k):
            raise AssertionError("보호된 항목은 네트워크를 전혀 건드리면 안 됨")

        orig_from_original = fill_images.from_original
        fill_images.from_original = boom
        try:
            fill_images.main()
        finally:
            fill_images.from_original = orig_from_original

        saved = json.loads(self.news_path.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["imageUrl"], "https://wsrv.nl/?url=manual.jpg")
        self.assertEqual(saved[1]["imageUrl"], "https://wsrv.nl/?url=already-found.jpg")

    def test_time_budget_stops_processing_early(self):
        items = [item(id=f"news-{n}", link=f"https://example.com/{n}") for n in range(5)]
        self.news_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        fill_images.NEWS = self.news_path
        fill_images.TIME_BUDGET_SEC = -1  # 음수 예산 -> 첫 항목 전에 항상 중단됨을 보장

        def boom(*a, **k):
            raise AssertionError("시간 예산 초과 후에는 네트워크 함수가 호출되면 안 됨")

        orig_from_original = fill_images.from_original
        fill_images.from_original = boom
        try:
            fill_images.main()
        finally:
            fill_images.from_original = orig_from_original

        saved = json.loads(self.news_path.read_text(encoding="utf-8"))
        self.assertTrue(all("imageUrl" not in i for i in saved))


class HardTimeBudgetTests(unittest.TestCase):
    """시간 예산이 개별 HTTP 요청에도 전파되고, 예산이 남은 항목은 시도 자체를 하지 않으며,
    예산 도중 중단된 항목에는 imageTried 마크가 남지 않음을 확인."""

    def setUp(self):
        self._orig_deadline = fill_images.DEADLINE

    def tearDown(self):
        fill_images.DEADLINE = self._orig_deadline

    def test_http_get_raises_before_network_when_budget_exhausted(self):
        import time as time_mod
        fill_images.DEADLINE = time_mod.monotonic() - 1  # 이미 지남

        def boom(*a, **k):
            raise AssertionError("예산이 없으면 실제 요청을 시도하면 안 됨")

        with mock.patch.object(fill_images.urllib.request, "urlopen", side_effect=boom):
            with self.assertRaises(fill_images.BudgetExceeded):
                fill_images.http_get("https://example.com/x.jpg")

    def test_http_get_caps_timeout_to_remaining_budget(self):
        import time as time_mod
        fill_images.DEADLINE = time_mod.monotonic() + 3  # 남은 시간 약 3초 (기본 timeout=20보다 짧음)
        captured = {}

        class FakeHeaders:
            def get(self, key, default=""):
                return default

            def get_content_charset(self):
                return "utf-8"

        class FakeResp:
            headers = FakeHeaders()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def geturl(self):
                return "https://example.com/x.jpg"

            def read(self, limit):
                return b""

        def fake_urlopen(req, timeout=None):
            captured["timeout"] = timeout
            return FakeResp()

        with mock.patch.object(fill_images.urllib.request, "urlopen", side_effect=fake_urlopen):
            fill_images.http_get("https://example.com/x.jpg", timeout=20)
        self.assertLessEqual(captured["timeout"], 3)
        self.assertGreater(captured["timeout"], 0)

    def test_budget_interrupted_item_gets_no_tried_marker(self):
        """처리 도중 BudgetExceeded가 나면 해당 항목은 완전히 손대지 않은 상태로 남아야 함
        (imageTried 마크 없음 — 다음 실행에서 RETRY_DAYS 대기 없이 바로 재시도)."""
        import time as time_mod
        import uuid
        holder = Path(__file__).resolve().parent / ".tmp"
        holder.mkdir(exist_ok=True)
        news_path = holder / f"news-budget-{int(time_mod.time()*1000)}-{uuid.uuid4().hex[:6]}.json"
        items = [item(id="news-1", link="https://example.com/1")]
        news_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

        orig_news = fill_images.NEWS
        orig_budget = fill_images.TIME_BUDGET_SEC
        orig_from_original = fill_images.from_original
        fill_images.NEWS = news_path
        fill_images.TIME_BUDGET_SEC = 1200  # 충분한 예산으로 시작하지만, 처리 중 강제로 BudgetExceeded 발생시킴

        def raise_budget(it):
            raise fill_images.BudgetExceeded("test")

        fill_images.from_original = raise_budget
        try:
            fill_images.main()
        finally:
            fill_images.NEWS = orig_news
            fill_images.TIME_BUDGET_SEC = orig_budget
            fill_images.from_original = orig_from_original
            if news_path.exists():
                news_path.unlink()

        saved = json.loads(news_path.read_text(encoding="utf-8")) if news_path.exists() else items
        self.assertNotIn("imageTried", saved[0])
        self.assertNotIn("imageUrl", saved[0])


if __name__ == "__main__":
    unittest.main()
