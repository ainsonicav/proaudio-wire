"""scripts/reconcile_generated.py 테스트 (fill-images.yml 신뢰성 수정).

배경: 대기열에 밀려 있던 fill-images 실행이 오래된 체크아웃 SHA 위에서 커밋을
시도했는데, 그 사이 다른 실행이 먼저 더 새 stats.json을 올려 둬 `git pull
--rebase`가 충돌로 반복 실패했습니다(5번 모두 동일하게 실패, 사진은 처리됐지만
아무것도 반영 못 함). 이 테스트는 그 복구 로직(scripts/reconcile_generated.py)을
실제 git 없이(오프라인) 검증합니다 — git 호출이 필요한 부분(list_conflicted_files,
main())은 monkeypatch로 가짜 충돌 목록을 주입합니다.

다루는 범위:
  - "순수 생성 파일"(stats.json/rss.xml/sitemap.xml/n/*.html) 경로만 재생성
    대상으로 분류되고, index.html은 정적 뼈대와 생성 구간이 섮인 파일이라
    의도적으로 제외됨(classify/is_generated_path) — index.html이 충돌 목록에
    있으면 무조건 원본 충돌로 취급해 즉시 실패.
  - n/*.html도 n/ 바로 아래의 .html 파일만 허용하고, n/ 중첩 경로·
    .html이 아닌 파일·디렉터리 자체는 제외(임의 경로를 무한범 허용하지 않음).
  - news.json·index.html·coupang_picks.html 등 원본/수동 파일 충돌이 하나라도
    섞이면 아무 파일도 건드리지 않고 실패(자동으로 "해결"하지 않음).
  - 생성 파일만 충돌했을 때 regenerate가 "그 순간 news.json으로 다시 계산한
    값"을 쓰고, 어느 쪽(로컬/원격)의 오래된 내용도 그대로 남기지 않음(stale
    stats 없음).
  - 2차 방어선: news.json이나 index.html에 미해결 git 충돌 표시(<<<<<<< 등)가
    남아 있으면 classify 통과 여부와 무관하게 regenerate가 즉시 중단(has_conflict_markers).
  - main()이 git 충돌 목록에 따라 올바른 종료 코드를 돌려줌(호출자인
    fill-images.yml의 재시도 루프가 "고칠 수 있는 충돌"과 "즉시 실패해야 하는
    충돌"을 구분하는 근거).
  - fill-images.yml 워크플로 파일 자체에 대한 정적(static) 검사: 체크아웃이 고정 SHA
    대신 ref: main을 쓰는지, rebase --continue가 TTY 없는 CI에서 멈추지 않도록
    GIT_EDITOR=true로 돌는지(지원되지 않을 수 있는 --no-edit를 쓰지 않는지), 충돌 발생
    시 reconcile_generated.py를 호출하는지 확인(test_fill_images_workflow_static_invariants).

네트워크·실제 git 호출 없음. 실제 news.json(128건 데이터)은 건드리지 않고
모두 tests/.tmp 임시 폴더의 소규모 fixture로만 검사합니다.
"""
import json
import shutil
import time
import unittest
import uuid
from pathlib import Path

import conftest_helper  # noqa: F401  (scripts/ 를 sys.path에 추가)

import build  # noqa: E402
import reconcile_generated as rg  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "fill-images.yml"


def make_item(**over):
    base = {
        "id": "news-1",
        "date": "2026-09-20",
        "company": "Example Co",
        "brand": "ExampleBrand",
        "type": "신제품",
        "summary": "테스트용 요약입니다.",
        "link": "https://example.com/news/1",
        "category": "프로오디오",
        "productName": "ExampleBrand X1",
    }
    base.update(over)
    return base


class GeneratedPathClassificationTests(unittest.TestCase):
    """"순수" 생성 파일(stats/rss/sitemap/n/*.html)만 재생성 대상으로 잡히는지 확인.
    index.html은 AGENTS.md에서는 "생성 파일"로 분류되지만, 정적 뼈대와 생성 구간이
    섮인 파일이라 자동 충돌 해결 허용 목록에서는 의도적으로 제외됨."""

    def test_known_generated_paths_are_eligible(self):
        for p in ("stats.json", "rss.xml", "sitemap.xml",
                  "n/news-5.html", "n/news-200.html"):
            self.assertTrue(rg.is_generated_path(p), p)

    def test_index_html_is_excluded_even_though_it_is_build_generated(self):
        """index.html은 build.py가 써내는 파일이지만, 정적 뼈대와 생성 구간이
        한 파일에 섮여 있어 충돌 시 자동 해결 대상에서 제외해야 함(독립 검토
        지적 사항) — 원본 보호가 자동 해결 범위보다 우선."""
        self.assertFalse(rg.is_generated_path("index.html"))

    def test_source_and_manual_paths_are_not_eligible(self):
        for p in ("news.json", "notices.json", "incoming/new.json", "index.html",
                   "coupang_picks.html", "scripts/build.py", "scripts/fill_images.py",
                   "docs/news-pipeline.md", "AGENTS.md", "README.md"):
            self.assertFalse(rg.is_generated_path(p), p)

    def test_nested_or_non_html_paths_under_n_are_not_eligible(self):
        """n/ 디렉터리 통째가 아니라 n/*.html 패턴만 허용 — 임의 경로를
        무한범 생성 파일로 오인하지 않음."""
        for p in ("n", "n/sub/news-1.html", "n/news-1.txt", "n/"):
            self.assertFalse(rg.is_generated_path(p), p)

    def test_windows_style_separators_in_n_dir_are_recognized(self):
        # git은 보통 '/'를 쓰지만, 방어적으로 '\\'도 생성 파일로 인식해야 함
        self.assertTrue(rg.is_generated_path("n\\news-7.html"))

    def test_classify_splits_mixed_conflict_list(self):
        generated, other = rg.classify(["stats.json", "news.json", "n/news-1.html", "incoming/new.json"])
        self.assertEqual(generated, ["stats.json", "n/news-1.html"])
        self.assertEqual(other, ["news.json", "incoming/new.json"])

    def test_index_html_conflict_is_classified_as_other(self):
        generated, other = rg.classify(["stats.json", "index.html"])
        self.assertEqual(generated, ["stats.json"])
        self.assertEqual(other, ["index.html"])


class ConflictMarkerGuardTests(unittest.TestCase):
    def test_detects_standard_three_line_marker(self):
        text = "a\n<<<<<<< HEAD\nmine\n=======\ntheirs\n>>>>>>> origin/main\nb\n"
        self.assertTrue(rg.has_conflict_markers(text))

    def test_clean_text_has_no_markers(self):
        self.assertFalse(rg.has_conflict_markers('{"a": 1}\n'))

    def test_does_not_false_positive_on_similar_but_shorter_sequences(self):
        self.assertFalse(rg.has_conflict_markers("====\n<<<\n"))


class ReconcileFixture(unittest.TestCase):
    """실제 scripts/build.py·pages.py를 그대로 불러 쓰되, news.json·stats.json 등
    데이터 파일만 tests/.tmp 임시 폴더에 복사해 검사 (저장소 원본 데이터는 불변)."""

    def setUp(self):
        holder = REPO_ROOT / "tests" / ".tmp"
        holder.mkdir(exist_ok=True)
        self.tmp = holder / f"pw-wfrecovery-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir()
        shutil.copy(REPO_ROOT / "index.html", self.tmp / "index.html")
        if (REPO_ROOT / "coupang_picks.html").exists():
            shutil.copy(REPO_ROOT / "coupang_picks.html", self.tmp / "coupang_picks.html")
        self.items = [
            make_item(id="news-1", brand="Alpha", link="https://example.com/a"),
            make_item(id="news-2", brand="Beta", link="https://example.com/b", date="2026-09-25"),
        ]
        (self.tmp / "news.json").write_text(
            json.dumps(self.items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # 고의로 "오래된/다른" stats.json을 심어 둠 — merge 직후 작업 디렉터리에
        # 남아 있을 법한, news.json 내용과 안 맞는 생성 파일 상태를 흉내냄.
        self.stale_stats = {
            "generated_at": "2000-01-01T00:00:00Z",
            "window_days": {"week": 7, "month": 30},
            "counts": {"week": 999, "month": 999, "total": 999},
            "top_brands_week": [{"brand": "StaleBrand", "count": 999}],
            "category_ratio_week": [],
            "category_ratio_month": [],
        }
        (self.tmp / "stats.json").write_text(
            json.dumps(self.stale_stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (self.tmp / "rss.xml").write_text("<rss>stale</rss>", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class GeneratedOnlyConflictTests(ReconcileFixture):
    def test_regenerate_recomputes_stats_from_current_news_json_not_stale_copy(self):
        news_before = (self.tmp / "news.json").read_text(encoding="utf-8")
        items = rg.regenerate(self.tmp)
        self.assertEqual(len(items), 2)

        saved_stats = json.loads((self.tmp / "stats.json").read_text(encoding="utf-8"))
        # 심어 둔 오래된/엉뚱한 값이 하나도 남아 있지 않아야 함 (stale stats 없음)
        self.assertNotEqual(saved_stats["counts"], self.stale_stats["counts"])
        self.assertNotEqual(saved_stats["generated_at"], self.stale_stats["generated_at"])
        self.assertNotEqual(saved_stats["top_brands_week"], self.stale_stats["top_brands_week"])

        # 지금 news.json을 build.compute_stats로 직접 계산한 값과 (타임스탬프 제외) 일치해야 함
        expected = build.compute_stats(json.loads(news_before))
        for key in ("window_days", "counts", "top_brands_week", "category_ratio_week", "category_ratio_month"):
            self.assertEqual(saved_stats[key], expected[key], key)

        # news.json 자체는 절대 건드리지 않음
        self.assertEqual((self.tmp / "news.json").read_text(encoding="utf-8"), news_before)

    def test_rss_is_regenerated_not_left_stale(self):
        rg.regenerate(self.tmp)
        rss = (self.tmp / "rss.xml").read_text(encoding="utf-8")
        self.assertNotIn("stale", rss)
        self.assertIn("<rss", rss)

    def test_regenerate_still_updates_index_html_prerender_when_index_itself_is_clean(self):
        """index.html은 자동 충돌 해결 대상은 아니지만, index.html 자체가 충돌
        없으면(=일반적인 재빌드 상황) 여전히 최신 news.json 기준으로 PRERENDER 구간이
        다시 계산되어야 함(그렇지 않으면 index.html이 merge된 news.json과 어긋나게 남음)."""
        rg.regenerate(self.tmp)
        index_html = (self.tmp / "index.html").read_text(encoding="utf-8")
        self.assertIn("Alpha", index_html)
        self.assertIn("Beta", index_html)

    def test_reconcile_with_only_generated_conflicts_succeeds(self):
        # stage()는 실제 `git add`를 호출함 — 이 샌드박스에는 git 바이너리가 없으므로(과제
        # 설명에 명시된 제약) git 호출 자체는 실제 git으로 확인할 수 없음 — 여기서는
        # stage가 정확히 한 번, 맞는 경로 집합으로 호출되는지만 검증(regenerate의 실제
        # 결과는 파일 내용 비교로 다른 테스트에서 따로 검증함).
        staged_calls = []
        orig_stage = rg.stage
        rg.stage = lambda root: staged_calls.append(root)
        try:
            generated, other, items = rg.reconcile(self.tmp, ["stats.json", "rss.xml", "n/news-9.html"])
        finally:
            rg.stage = orig_stage
        self.assertEqual(other, [])
        self.assertEqual(sorted(generated), ["n/news-9.html", "rss.xml", "stats.json"])
        self.assertEqual(len(items), 2)
        self.assertEqual(staged_calls, [self.tmp])

    def test_empty_conflict_list_is_a_no_op(self):
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        generated, other, items = rg.reconcile(self.tmp, [])
        self.assertIsNone(items)
        self.assertEqual(other, [])
        # 아무 것도 재생성하지 않았으므로 심어 둔 stale 값이 그대로여야 함
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)


class SourceConflictNeverAutoResolvedTests(ReconcileFixture):
    """news.json(또는 다른 원본) 충돌이 섞이면 절대 자동으로 손대지 않아야 함."""

    def test_news_json_conflict_blocks_reconciliation_without_touching_any_file(self):
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        rss_before = (self.tmp / "rss.xml").read_text(encoding="utf-8")
        news_before = (self.tmp / "news.json").read_text(encoding="utf-8")

        generated, other, items = rg.reconcile(self.tmp, ["stats.json", "news.json"])

        self.assertEqual(other, ["news.json"])
        self.assertIsNone(items)
        # 생성 파일도 포함돼 있었지만, news.json이 섞였으므로 아무 것도 재생성하지 않음
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)
        self.assertEqual((self.tmp / "rss.xml").read_text(encoding="utf-8"), rss_before)
        self.assertEqual((self.tmp / "news.json").read_text(encoding="utf-8"), news_before)

    def test_coupang_picks_conflict_also_blocks_reconciliation(self):
        generated, other, items = rg.reconcile(self.tmp, ["coupang_picks.html", "stats.json"])
        self.assertEqual(other, ["coupang_picks.html"])
        self.assertIsNone(items)

    def test_regenerate_rejects_corrupt_merged_news_json_without_writing_partial_output(self):
        """merge된 news.json 자체가 build.validate 기준으로 손상돼 보이면(예: 필수
        필드 누락) 재생성을 강행하지 않고 중단 — 깨진 데이터 기준 stats.json을
        새로 "정답"인 양 써넣지 않음."""
        broken = [{"id": "news-1"}]  # 필수 필드 대부분 누락
        (self.tmp / "news.json").write_text(json.dumps(broken), encoding="utf-8")
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        with self.assertRaises(RuntimeError):
            rg.regenerate(self.tmp)
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)

    def test_regenerate_rejects_news_json_with_leftover_conflict_markers(self):
        """2차 방어선: classify를 거치지 않고 regenerate가 직접 불리더라도,
        news.json에 미해결 git 충돌 표시가 남아 있으면 그 내용을 "정상"으로 오인해
        JSON파싱을 시도하기 전에 먼저 거부해야 함."""
        conflicted = ("<<<<<<< HEAD\n[]\n=======\n[{}]\n>>>>>>> origin/main\n")
        (self.tmp / "news.json").write_text(conflicted, encoding="utf-8")
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        with self.assertRaises(RuntimeError) as cm:
            rg.regenerate(self.tmp)
        self.assertIn("충돌", str(cm.exception))
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)

    def test_regenerate_rejects_index_html_with_leftover_conflict_markers(self):
        """index.html은 자동 충돌 해결 대상이 아니므로 평소에는 classify()가 이미
        막지만, regenerate()가 독립적으로 다시 한번 검사해 길린 정적 콘텐츠 사이에
        남은 충돌 표시를 기준으로 재계산·커밋하지 않도록 막아야 함."""
        broken_index = "<html><<<<<<< HEAD\n<p>a</p>\n=======\n<p>b</p>\n>>>>>>> main\n</html>"
        (self.tmp / "index.html").write_text(broken_index, encoding="utf-8")
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        with self.assertRaises(RuntimeError) as cm:
            rg.regenerate(self.tmp)
        self.assertIn("index.html", str(cm.exception))
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)


class MainExitCodeContractTests(ReconcileFixture):
    """fill-images.yml의 재시도 루프는 이 종료 코드로 "재생성 성공(이어가기)"과
    "자동으로 못 고치는 충돌(즉시 실패)"을 구분함. git 호출은 monkeypatch로 대체."""

    def _run_main_with_fake_conflicts(self, conflicts):
        orig_root, orig_list = rg.ROOT, rg.list_conflicted_files
        rg.ROOT = self.tmp
        rg.list_conflicted_files = lambda root: conflicts
        try:
            return rg.main()
        finally:
            rg.ROOT = orig_root
            rg.list_conflicted_files = orig_list

    def test_no_conflicts_returns_zero_without_touching_files(self):
        stats_before = (self.tmp / "stats.json").read_text(encoding="utf-8")
        code = self._run_main_with_fake_conflicts([])
        self.assertEqual(code, 0)
        self.assertEqual((self.tmp / "stats.json").read_text(encoding="utf-8"), stats_before)

    def test_generated_only_conflicts_return_zero_and_regenerate(self):
        # stage()의 실제 `git add` 호출은 이 샌드박스에 git이 없어 검증 불가(과제 설명에
        # 명시된 제약) — 여기서는 main()이 올바른 종료 코드와 재생성 결과만 검증하고,
        # stage 호출 자체는 no-op으로 대체.
        orig_stage = rg.stage
        rg.stage = lambda root: None
        try:
            code = self._run_main_with_fake_conflicts(["stats.json", "rss.xml"])
        finally:
            rg.stage = orig_stage
        self.assertEqual(code, 0)
        saved_stats = json.loads((self.tmp / "stats.json").read_text(encoding="utf-8"))
        self.assertNotEqual(saved_stats["counts"], self.stale_stats["counts"])

    def test_source_conflict_returns_distinct_nonzero_code_not_retry_loop(self):
        """2는 "자동으로 못 고침 → 즉시 중단하고 실패" 신호. 네트워크류 실패와
        같은 코드를 쓰면 워크플로가 고쳐지지 않는 충돌을 계속 재시도하게 됨."""
        code = self._run_main_with_fake_conflicts(["news.json"])
        self.assertEqual(code, 2)

    def test_git_list_failure_returns_distinct_code_from_content_conflict(self):
        orig_root, orig_list = rg.ROOT, rg.list_conflicted_files

        def boom(root):
            raise RuntimeError("git 호출 실패(네트워크 등)")

        rg.ROOT = self.tmp
        rg.list_conflicted_files = boom
        try:
            code = rg.main()
        finally:
            rg.ROOT = orig_root
            rg.list_conflicted_files = orig_list
        self.assertEqual(code, 3)
        self.assertNotEqual(code, 2)  # 네트워크성 실패를 "원본 충돌"로 오분류하지 않음


class FillImagesWorkflowStaticInvariantTests(unittest.TestCase):
    """fill-images.yml 워크플로 파일 자체를 텍스트로 검사(YAML 파서 없이, 정규식 기반).
    실제 워크플로 실행(GitHub Actions)은 이 샌드박스에서 할 수 없으므로, 독립
    검토에서 지적된 위험한 패턴(충돌 재시도 명령어가 다시 슬먹어들어가는 것을
    막는 최소한의 회귀 가드리다."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_checkout_pins_to_latest_main_branch_not_fixed_trigger_sha(self):
        """고정 SHA 대신 ref: main을 써야 대기열에서 따라잊는 실행이 오래된
        트리거 SHA에 멈물리 않음 (fetch/reset --hard 등 없이도 actions/checkout
        자체 옵션으로 해결 — 더 적은 변경)."""
        self.assertIn("ref: main", self.text)

    def test_rebase_continue_uses_git_editor_true_not_unsupported_flag(self):
        """git rebase --continue는 git 버전에 따라 --no-edit를 지원하지 않을 수
        있으므로, TTY 없는 CI에서도 편집기가 열리지 않도록 GIT_EDITOR=true로 돌려야 함."""
        self.assertIn("GIT_EDITOR=true git rebase --continue", self.text)
        self.assertNotIn("rebase --continue --no-edit", self.text)

    def test_invokes_reconcile_generated_script_on_conflict(self):
        self.assertIn("scripts/reconcile_generated.py", self.text)

    def test_never_force_pushes(self):
        self.assertNotIn("push --force", self.text)
        self.assertNotIn("push -f ", self.text)
        self.assertNotIn("-f origin", self.text)

    def test_does_not_blindly_retry_identical_conflict_five_times(self):
        """생성 파일이 아닌 충돌(news.json/index.html 등)은 재시도 루프 안에서
        즉시 exit 1로 빠져나가야 함 — 루프 전체를 5번 같은 충돌로 돌지 않음."""
        marker = "news.json/index.html 등 원본 충돌이 있거나 재생성이 실패함"
        self.assertIn(marker, self.text)
        idx = self.text.index(marker)
        # 그 직후 블록에 exit 1이 있어야 함(즉시 실패, sleep후 같은 시도 반복 아님)
        self.assertIn("exit 1", self.text[idx:idx + 400])

    def test_commit_step_never_blindly_stages_bare_index_as_trusted_without_build(self):
        """커밋 단계에서는 여전히 build.py를 먼저 돌려 index.html을 정상 생성한
        뒤에만 git add함(일반 커밋 경로에는 index.html이 포함되어야 함)."""
        self.assertIn("scripts/build.py", self.text)
        self.assertIn("git add -A news.json rss.xml sitemap.xml stats.json index.html n", self.text)


if __name__ == "__main__":
    unittest.main()
