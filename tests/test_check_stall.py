"""scripts/check_stall.py 오프라인 테스트 (네트워크·git 호출 없음)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_stall as cs  # noqa: E402


class LastAddedTest(unittest.TestCase):
    def test_photo_only_commits_do_not_count_as_new_story(self):
        data = {
            "c5": [{"id": "news-3"}, {"id": "news-2"}],  # 사진 채우기 (id 그대로)
            "c4": [{"id": "news-3"}, {"id": "news-2"}],  # 사진 채우기
            "c3": [{"id": "news-3"}, {"id": "news-2"}],  # news-3 추가된 커밋
            "c2": [{"id": "news-2"}],
        }
        commits = [("c5", 500), ("c4", 400), ("c3", 300), ("c2", 200)]
        self.assertEqual(cs.last_added(commits, data.get), ("c3", 300, 3))

    def test_single_commit(self):
        self.assertEqual(cs.last_added([("a", 10)], lambda s: [{"id": "news-7"}]), ("a", 10, 7))

    def test_empty(self):
        self.assertIsNone(cs.last_added([], lambda s: []))

    def test_max_id_ignores_bad_rows(self):
        self.assertEqual(cs.max_id([{"id": "news-12"}, {"id": "x"}, "junk", {"id": "news-9"}]), 12)
        self.assertEqual(cs.max_id({}), -1)


if __name__ == "__main__":
    unittest.main()
