"""notify_telegram.py 테스트. 실제 텔레그램 전송·자격증명·git 호출은 전혀 쓰지 않습니다 —
send_telegram과 git 조회 함수를 모두 가짜 함수로 바꿔치기해서 오프라인으로 검사합니다.

다루는 범위:
  - 새 소식 11건이 와도 예전처럼 10건에서 잘리지 않고 모두 처리됨 (배치로 나눠서)
  - 일시적 오류는 제한된 횟수만 재시도하고, 성공한 항목을 다시 보내는 중복 발송은 없음
  - BASE_SHA/HEAD_SHA가 둘 다 주어지면 작업 디렉터리(가변적인 체크아웃 상태)를 전혀
    읽지 않고 "정확한 두 커밋"의 news.json만 git show로 비교함
  - HEAD_SHA가 없을 때만(사람이 직접 실행) 작업 디렉터리 파일로 폴백
"""
import unittest
from unittest import mock

import conftest_helper  # noqa: F401

import notify_telegram as nt  # noqa: E402


def make_item(i):
    return {
        "id": f"news-{i}",
        "brand": "ExampleBrand",
        "productName": f"Product {i}",
        "type": "신제품",
        "summary": "요약",
        "link": f"https://example.com/{i}",
        "isDomestic": i % 2 == 0,
    }


def _env_stub(values):
    def _get(key, default=""):
        return values.get(key, default)
    return _get


class NoTruncationTests(unittest.TestCase):
    def setUp(self):
        self._orig_batch_size = nt.BATCH_SIZE
        nt.BATCH_SIZE = 5  # 11건이 여러 배치에 걸치는지 확실히 보려고 작게 설정
        self._orig_send_pause = nt.SEND_PAUSE_SEC
        self._orig_batch_pause = nt.BATCH_PAUSE_SEC
        nt.SEND_PAUSE_SEC = 0
        nt.BATCH_PAUSE_SEC = 0

    def tearDown(self):
        nt.BATCH_SIZE = self._orig_batch_size
        nt.SEND_PAUSE_SEC = self._orig_send_pause
        nt.BATCH_PAUSE_SEC = self._orig_batch_pause

    def test_11_candidates_are_all_attempted_not_capped_at_10(self):
        current = [make_item(i) for i in range(11)]
        sent_ids = []

        def fake_send(token, chat_id, text):
            sent_ids.append(text)
            return True, ""

        with mock.patch.object(nt, "get_news_at_commit", return_value=[]), \
             mock.patch.object(nt, "send_telegram_with_retry", side_effect=fake_send), \
             mock.patch.object(nt.json, "load", return_value=current), \
             mock.patch("builtins.open", mock.mock_open()), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
             })):
            nt.main()

        self.assertEqual(len(sent_ids), 11)  # 10건에서 잘리지 않음


class RetryNoDuplicateReplayTests(unittest.TestCase):
    def test_transient_failure_is_retried_then_succeeds(self):
        calls = {"n": 0}

        def flaky(token, chat_id, text):
            calls["n"] += 1
            if calls["n"] == 1:
                return False, "HTTP 503: 일시 오류", 503
            return True, "", 200

        with mock.patch.object(nt, "send_telegram", side_effect=flaky), \
             mock.patch.object(nt.time, "sleep", return_value=None):
            ok, why = nt.send_telegram_with_retry("t", "c", "msg")
        self.assertTrue(ok)
        self.assertEqual(calls["n"], 2)  # 내부에서 1번 더 재시도했을 뿐, 외부에서 다시 안 부름

    def test_permanent_failure_is_not_retried(self):
        calls = {"n": 0}

        def perm_fail(token, chat_id, text):
            calls["n"] += 1
            return False, "HTTP 400: chat not found", 400

        with mock.patch.object(nt, "send_telegram", side_effect=perm_fail):
            ok, why = nt.send_telegram_with_retry("t", "c", "msg")
        self.assertFalse(ok)
        self.assertEqual(calls["n"], 1)  # 영구 오류는 재시도하지 않음

    def test_exhausts_retries_and_gives_up(self):
        calls = {"n": 0}

        def always_503(token, chat_id, text):
            calls["n"] += 1
            return False, "HTTP 503", 503

        with mock.patch.object(nt, "send_telegram", side_effect=always_503), \
             mock.patch.object(nt.time, "sleep", return_value=None):
            ok, why = nt.send_telegram_with_retry("t", "c", "msg")
        self.assertFalse(ok)
        self.assertEqual(calls["n"], nt.MAX_TRANSIENT_RETRIES + 1)

    def test_each_item_calls_retry_wrapper_exactly_once_no_outer_replay(self):
        """main()이 항목마다 send_telegram_with_retry를 정확히 한 번만 부르는지 확인
        (성공한 항목을 호출부에서 또 부르는 중복 발송이 없음)."""
        current = [make_item(1), make_item(2)]
        call_ids = []

        def fake_send(token, chat_id, text):
            call_ids.append(text)
            return True, ""

        with mock.patch.object(nt, "get_news_at_commit", return_value=[]), \
             mock.patch.object(nt, "send_telegram_with_retry", side_effect=fake_send), \
             mock.patch.object(nt.json, "load", return_value=current), \
             mock.patch("builtins.open", mock.mock_open()), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
             })):
            nt.main()
        self.assertEqual(len(call_ids), 2)
        self.assertEqual(len(set(call_ids)), 2)  # 서로 다른 메시지(중복 아님)


class ShaPinDiffTests(unittest.TestCase):
    """BASE_SHA/HEAD_SHA로 정확한 두 커밋을 고정 비교하는지 확인 (리뷰 피드백 반영)."""

    def test_base_sha_used_for_previous_lookup(self):
        current = [make_item(1)]
        with mock.patch.object(nt, "get_news_at_commit", return_value=[]) as m, \
             mock.patch.object(nt, "send_telegram_with_retry", return_value=(True, "")), \
             mock.patch.object(nt.json, "load", return_value=current), \
             mock.patch("builtins.open", mock.mock_open()), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
                 "BASE_SHA": "deadbeef1234",
             })):
            nt.main()
        m.assert_called_once_with("deadbeef1234")  # head_sha 없음 -> current는 작업 디렉터리 폴백

    def test_falls_back_to_head_caret_when_base_sha_missing(self):
        current = [make_item(1)]
        with mock.patch.object(nt, "get_news_at_commit", return_value=[]) as m, \
             mock.patch.object(nt, "send_telegram_with_retry", return_value=(True, "")), \
             mock.patch.object(nt.json, "load", return_value=current), \
             mock.patch("builtins.open", mock.mock_open()), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
             })):
            nt.main()
        m.assert_called_once_with("HEAD^")

    def test_head_sha_pins_current_to_exact_commit_not_working_tree(self):
        """HEAD_SHA가 주어지면 작업 디렉터리 파일(json.load/open)을 전혀 읽지 않고,
        git show로 그 정확한 커밋만 읽어야 함 — 체크아웃된 main이 그 사이 더
        앞서 나가 있어도(예: fill-images 커밋이 끼어들어도) 영향받지 않음."""
        by_ref = {
            "deadbeef1234": [],  # base: 추가 전
            "cafebabe5678": [make_item(1), make_item(2)],  # head: 추가 직후 정확한 커밋
        }

        def fake_show(ref):
            return by_ref.get(ref, [])

        sent = []

        def fake_send(token, chat_id, text):
            sent.append(text)
            return True, ""

        with mock.patch.object(nt, "get_news_at_commit", side_effect=fake_show) as m, \
             mock.patch.object(nt, "send_telegram_with_retry", side_effect=fake_send), \
             mock.patch.object(nt.json, "load", side_effect=AssertionError("작업 디렉터리를 읽으면 안 됨")), \
             mock.patch("builtins.open", side_effect=AssertionError("작업 디렉터리를 읽으면 안 됨")), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
                 "BASE_SHA": "deadbeef1234", "HEAD_SHA": "cafebabe5678",
             })):
            nt.main()

        self.assertEqual(len(sent), 2)
        m.assert_any_call("deadbeef1234")
        m.assert_any_call("cafebabe5678")

    def test_head_sha_mid_sequence_commit_not_confused_with_later_main(self):
        """HEAD_SHA가 가리키는 커밋과, 그 이후 main에 더 쌓인 상태(예: 사진 채우기 커밋)를
        섞지 않는지 확인 — get_news_at_commit이 항상 넘겨준 ref로만 조회됨을 검증."""
        history = {
            "base": [],
            "add_commit": [make_item(1)],
            # main은 이후 더 나아갔지만(사진 채우기 커밋), telegram-notify는
            # head_sha=add_commit 기준으로만 비교해야 함.
            "later_main": [make_item(1)],  # 같은 id, 사진만 채워짐(새 id 없음)
        }

        def fake_show(ref):
            return history[ref]

        sent = []

        def fake_send(token, chat_id, text):
            sent.append(text)
            return True, ""

        with mock.patch.object(nt, "get_news_at_commit", side_effect=fake_show), \
             mock.patch.object(nt, "send_telegram_with_retry", side_effect=fake_send), \
             mock.patch.object(nt.os.environ, "get", side_effect=_env_stub({
                 "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@proaudiowire",
                 "BASE_SHA": "base", "HEAD_SHA": "add_commit",
             })):
            nt.main()
        self.assertEqual(len(sent), 1)  # news-1 한 건만, later_main 상태와 섞이지 않음


if __name__ == "__main__":
    unittest.main()
