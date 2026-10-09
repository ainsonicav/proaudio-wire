"""build.py 단위/통합 테스트. 네트워크를 쓰지 않고(오프라인), 실제 news.json(128건)은
전혀 건드리지 않습니다 — 모두 tmp 임시 폴더에 복사한 소규모 가짜(fixture) 데이터로만 검사합니다.

다루는 범위:
  - 새로 들어오는 항목(incoming) 전용 검사: https 절대 URL, productName/evidence 중 하나 필수
  - 과거 기록은 새 검사 기준으로 재검사되지 않음(기존 128건 스키마 불변)
  - 원문 링크 중복(충돌) 건너뛰기, id 번호 충돌 없이 순차 부여
  - 검사 실패 시 news.json 파일이 전혀 바뀌지 않음(부분 저장/조용한 수용 없음)
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import conftest_helper  # noqa: F401  (scripts/ 를 sys.path에 추가)

import build  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_item(**over):
    base = {
        "date": "2026-09-20",
        "company": "Example Co",
        "brand": "ExampleBrand",
        "type": "신제품",
        "summary": "테스트용 요약입니다.",
        "link": "https://example.com/news/1",
        "category": "프로오디오",
        "productName": "ExampleBrand X1",
        "evidence": "원문 기사에서 발췌: \"ExampleBrand X1 공식 출시\"",
        "isDomestic": False,
    }
    base.update(over)
    return base


class ValidateIncomingTests(unittest.TestCase):
    def test_accepts_item_with_evidence_and_https(self):
        errs = build.validate_incoming([make_item()])
        self.assertEqual(errs, [])

    def test_accepts_item_with_only_product_name(self):
        errs = build.validate_incoming([make_item(evidence="")])
        self.assertEqual(errs, [])

    def test_accepts_item_with_only_evidence(self):
        errs = build.validate_incoming([make_item(productName="")])
        self.assertEqual(errs, [])

    def test_rejects_http_only_link(self):
        errs = build.validate_incoming([make_item(link="http://example.com/news/1")])
        self.assertEqual(len(errs), 1)
        self.assertIn("https", errs[0])

    def test_accepts_http_for_allowed_domain(self):
        for link in ("http://ntusys.com/inc/product_view.asp?nnum=55",
                     "http://www.ntusys.com/", "http://NTUSYS.com/"):
            self.assertEqual(build.validate_incoming([make_item(link=link)]), [], link)

    def test_rejects_http_for_lookalike_or_sub_domain(self):
        for link in ("http://ntusys.com.evil.example/", "http://evilntusys.com/",
                     "http://news.ntusys.com/", "ftp://ntusys.com/"):
            self.assertEqual(len(build.validate_incoming([make_item(link=link)])), 1, link)

    def test_rejects_missing_evidence_and_product_name(self):
        errs = build.validate_incoming([make_item(productName="", evidence="")])
        self.assertEqual(len(errs), 1)
        self.assertIn("productName", errs[0])

    def test_does_not_touch_historical_items(self):
        """validate_incoming은 fresh(새 항목) 리스트만 보고, 과거 기록(validate)의
        일반 검사 규칙(https 강제 없음)은 그대로 유지됨을 확인."""
        historical = {
            "id": "news-1", "date": "2020-01-01", "company": "Old Co", "brand": "Old",
            "type": "신제품", "summary": "옛날 소식", "link": "http://old.example.com/1",
            "category": "기타",
        }
        # 과거 기록은 generic validate()만 통과하면 됨 (http도 허용)
        self.assertEqual(build.validate([historical]), [])
        # validate_incoming은 fresh 리스트에 넣지 않는 한 과거 기록을 검사하지 않음
        self.assertEqual(build.validate_incoming([]), [])


class AddDedupTests(unittest.TestCase):
    def test_skips_duplicate_link(self):
        existing = [{**make_item(link="https://example.com/dup"), "id": "news-5"}]
        incoming_path = _write_incoming([make_item(link="https://example.com/dup", productName="Dup Product")])
        try:
            merged, fresh = build.add(existing, incoming_path)
        finally:
            os.unlink(incoming_path)
        self.assertEqual(len(fresh), 0)
        self.assertEqual(len(merged), 1)

    def test_assigns_sequential_ids_without_collision(self):
        existing = [{**make_item(link="https://example.com/old"), "id": "news-7"}]
        incoming_path = _write_incoming([
            make_item(link="https://example.com/new-1", productName="P1"),
            make_item(link="https://example.com/new-2", productName="P2"),
        ])
        try:
            merged, fresh = build.add(existing, incoming_path)
        finally:
            os.unlink(incoming_path)
        new_ids = sorted(i["id"] for i in fresh)
        self.assertEqual(new_ids, ["news-8", "news-9"])
        # id 충돌 없음: 전체 id가 모두 유일
        all_ids = [i["id"] for i in merged]
        self.assertEqual(len(all_ids), len(set(all_ids)))


def _write_incoming(items):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    return path


class CliIntegrationTests(unittest.TestCase):
    """실제 scripts/build.py를 subprocess로 돌려 --add 경로 전체(검사 실패 시 파일 불변,
    통과 시 정상 반영 + GITHUB_OUTPUT 기록)를 오프라인으로 검증. 네트워크 호출 없음."""

    def setUp(self):
        import time
        import uuid
        # tempfile.mkdtemp()가 만드는 폴더는 일부 새드박스 환경에서 자식 하위 mkdir이 막히는 사례가
        # 있어(ACL 상속 문제 추정) 일반 mkdir로 직접 만듭니다.
        holder = REPO_ROOT / "tests" / ".tmp"
        holder.mkdir(exist_ok=True)
        self.tmp = holder / f"pw-build-test-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir()
        (self.tmp / "scripts").mkdir()
        shutil.copy(REPO_ROOT / "scripts" / "build.py", self.tmp / "scripts" / "build.py")
        shutil.copy(REPO_ROOT / "scripts" / "pages.py", self.tmp / "scripts" / "pages.py")
        shutil.copy(REPO_ROOT / "index.html", self.tmp / "index.html")
        if (REPO_ROOT / "coupang_picks.html").exists():
            shutil.copy(REPO_ROOT / "coupang_picks.html", self.tmp / "coupang_picks.html")
        self.news_path = self.tmp / "news.json"
        self.base_items = [{**make_item(link="https://example.com/base"), "id": "news-1"}]
        self.news_path.write_text(json.dumps(self.base_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.gh_output = self.tmp / "gh_output.txt"
        self.gh_output.write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_add(self, incoming_items):
        incoming_path = self.tmp / "incoming_new.json"
        incoming_path.write_text(json.dumps(incoming_items, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ)
        env["GITHUB_OUTPUT"] = str(self.gh_output)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "scripts/build.py", "--add", str(incoming_path)],
            cwd=self.tmp, capture_output=True, text=True, encoding="utf-8", env=env,
        )
        return proc

    def _gh_output_values(self):
        out = {}
        for line in self.gh_output.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
        return out

    def test_valid_incoming_item_is_added_and_output_written(self):
        proc = self._run_add([make_item(link="https://example.com/new-item", productName="New Thing")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        saved = json.loads(self.news_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 2)
        self.assertEqual(self._gh_output_values().get("added_count"), "1")

    def test_invalid_incoming_item_rejected_without_touching_file(self):
        bad = make_item(link="http://example.com/insecure", productName="", evidence="")
        proc = self._run_add([bad])
        self.assertEqual(proc.returncode, 1)
        # 파일이 전혀 바뀌지 않아야 함 (조용히 통과시키지 않음)
        saved = json.loads(self.news_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, self.base_items)
        self.assertEqual(self._gh_output_values().get("added_count"), "0")
        self.assertIn("productName", proc.stdout)

    def test_duplicate_link_in_incoming_is_silently_skipped_not_an_error(self):
        proc = self._run_add([make_item(link="https://example.com/base", productName="Dup")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        saved = json.loads(self.news_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)  # 추가되지 않음(원문 중복)
        self.assertEqual(self._gh_output_values().get("added_count"), "0")


if __name__ == "__main__":
    unittest.main()
