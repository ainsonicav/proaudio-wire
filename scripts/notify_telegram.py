#!/usr/bin/env python3
"""news.json에 새로 추가된 항목만 골라 텔레그램 채널로 보냅니다.

GitHub Actions에서만 실행됩니다 (텔레그램 API는 자동화 환경에서 접속이
막혀 있어, GitHub 서버가 대신 보냅니다).

필요한 저장소 Secret (Settings > Secrets and variables > Actions > Secrets):
  TELEGRAM_BOT_TOKEN  - BotFather가 준 봇 토큰
  TELEGRAM_CHAT_ID    - 채널 사용자명, 예: @proaudiowire

동작:
  - 기본: 기준점(BASE_SHA, 없으면 HEAD^)과 비교 대상(HEAD_SHA, 없으면 현재 작업
    디렉터리)의 news.json을 "둘 다 git show로 정확한 커밋에서" 읽어 비교해 새 id만
    전송합니다. add-news.yml은 (1) 새 항목을 커밋하기 '직전'의 정확한 SHA를
    BASE_SHA로, (2) push가 성공한 '직후'의 정확한 SHA를 HEAD_SHA로 함께 넘깁니다.
    둘 다 정확한 commit SHA로 고정해야, 그 사이에(또는 그 이후에) 사진 채우기 같은
    다른 커밋이 끼어들어도 — 또는 이 작업이 실행되는 시점에 main 브랜치가 이미 더
    앞서 나가 있어도 — 항상 "그때 그 커밋"을 기준으로 비교합니다. HEAD_SHA 없이
    현재 작업 디렉터리(체크아웃된 main의 최신 상태, 가변적)를 읽으면 그 사이 끼어든
    변경이 뒤섞여 새 id 집합이 흔들릴 수 있습니다.
  - TEST_MESSAGE=1 : 새 소식과 상관없이 "연결 테스트" 메시지 1건 전송

새 항목은 개수 제한 없이 모두 보냅니다(예전에는 한 번에 최대 10건만 보내고
나머지는 조용히 버렸음). 대신 Telegram API 속도 제한을 지키기 위해 일정 개수씩
배치로 나누고 메시지 사이에 짧게 대기합니다.

일시적 오류(네트워크 예외, HTTP 429, 5xx)만 제한된 횟수로 재시도합니다. 이미
성공적으로 보낸 메시지를 다시 보내는 일(중복 발송)은 하지 않습니다 — 항목마다
전송 함수를 정확히 한 번만 호출하고, 그 호출 내부에서만 일시적 오류를 재시도합니다.

이 스크립트는 add-news.yml의 명시적 workflow_dispatch 신호로만 실행되도록
설계되었습니다(news.json push에 대한 on: push 트리거는 없음 — 사람이 news.json을
직접 고친 경우에는 워크플로 탭에서 수동으로 실행해야 합니다).

결과는 GitHub Actions 요약(annotation)에 남고, 설정 누락·전송 실패 시
작업을 실패로 표시합니다(원인 확인용).
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = "https://news.ainsonic.com"

# 한 번에 모아서 보낼 최대 건수(배치 크기)와 전송 간 대기 시간(초).
BATCH_SIZE = 20
BATCH_PAUSE_SEC = 2.0
SEND_PAUSE_SEC = 1.2
# 일시적(네트워크/429/5xx) 오류만 제한된 횟수로 재시도. 400대 단순 요청 오류
# (잘못된 chat_id, HTML 파싱 오류 등)는 재시도해도 같은 결과라 제외.
MAX_TRANSIENT_RETRIES = 2
RETRY_BACKOFF_SEC = 3.0


def notice(msg):
    print(f"::notice title=텔레그램 알림::{msg}", flush=True)


def error(msg):
    print(f"::error title=텔레그램 알림::{msg}", flush=True)


def load_json_text(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


def get_news_at_commit(ref):
    """정확한 commit ref의 news.json 내용을 git show로 직접 읽음(작업 디렉터리 상태나
    현재 체크아웃된 브랜치 포인터에 의존하지 않음). 없으면 빈 리스트."""
    try:
        out = subprocess.run(
            ["git", "show", f"{ref}:news.json"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return load_json_text(out.stdout)
    except subprocess.CalledProcessError:
        return []


# 하위 호환 별칭(기존 테스트/호출부 이름).
get_previous_news = get_news_at_commit


def get_current_news(head_ref):
    """head_ref가 있으면 그 정확한 커밋에서 읽고, 없으면 현재 작업 디렉터리의
    news.json 파일을 읽음(사람이 workflow_dispatch를 head_sha 없이 수동 실행한 경우)."""
    if head_ref:
        return get_news_at_commit(head_ref)
    return json.load(open(os.path.join(ROOT, "news.json"), encoding="utf-8"))


def escape_html(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(item):
    tag = {"신제품": "🆕 신제품", "업데이트": "🔧 업데이트", "행사": "📅 행사"}.get(
        item.get("type", ""), item.get("type", "소식")
    )
    domestic = "🇰🇷 " if item.get("isDomestic") else ""
    brand = escape_html(item.get("brand") or item.get("company") or "")
    name = escape_html(item.get("productName") or "")
    summary = escape_html(item.get("summary", ""))
    link = escape_html(item.get("link", ""))
    title = f"{domestic}<b>[{tag}] {brand}</b>"
    if name:
        title += f" — {name}"
    parts = [title, summary]
    if link:
        parts.append(f'<a href="{link}">원문 보기</a> · <a href="{SITE_URL}">PRO AUDIO WIRE</a>')
    return "\n\n".join(parts)


def _is_transient(status_code):
    """재시도해도 되는 일시적 실패인지 판단 (429 속도제한, 5xx 서버 오류, 네트워크 예외)."""
    if status_code is None:
        return True  # 연결/타임아웃 등 예외
    return status_code == 429 or 500 <= status_code < 600


def send_telegram(token, chat_id, text):
    """성공하면 (True, '', status_code), 실패하면 (False, 이유, status_code)를 돌려줌."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
            ok = bool(body.get("ok"))
            return (True, "", 200) if ok else (False, body.get("description", str(body)), 200)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return False, f"HTTP {e.code}: {body.get('description', '')}", e.code
        except Exception:  # noqa: BLE001
            return False, f"HTTP {e.code}", e.code
    except Exception as e:  # noqa: BLE001
        return False, f"요청 오류: {e}", None


def send_telegram_with_retry(token, chat_id, text):
    """일시적 오류만 제한된 횟수로 재시도. 성공한 항목은 다시 부르지 않으므로(호출측에서
    항목당 이 함수를 정확히 한 번만 호출) 중복 발송(replay)은 일어나지 않음."""
    attempt = 0
    while True:
        ok, why, status = send_telegram(token, chat_id, text)
        if ok or not _is_transient(status) or attempt >= MAX_TRANSIENT_RETRIES:
            return ok, why
        attempt += 1
        time.sleep(RETRY_BACKOFF_SEC * attempt)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if missing:
        error(
            "저장소 Secret이 비어 있습니다: " + ", ".join(missing)
            + " — Settings > Secrets and variables > Actions > 'Secrets' 탭(Variables 아님)에 "
            "정확한 이름으로 등록해 주세요."
        )
        sys.exit(1)

    if ":" not in token:
        error("TELEGRAM_BOT_TOKEN 형식이 이상합니다 (숫자:영문 형태여야 함).")
        sys.exit(1)
    if not (chat_id.startswith("@") or chat_id.lstrip("-").isdigit()):
        error(f"TELEGRAM_CHAT_ID는 @로 시작해야 합니다 (예: @proaudiowire). 현재 값 앞부분: {chat_id[:3]}...")
        sys.exit(1)

    if os.environ.get("TEST_MESSAGE") == "1":
        ok, why = send_telegram_with_retry(
            token, chat_id,
            "✅ <b>PRO AUDIO WIRE 연결 테스트</b>\n\n이 메시지가 보이면 새 소식 자동 알림이 정상 연결된 것입니다.\n"
            f'<a href="{SITE_URL}">news.ainsonic.com</a>',
        )
        if ok:
            notice(f"연결 테스트 메시지 전송 성공 → {chat_id}")
            return
        error(f"연결 테스트 전송 실패 ({chat_id}): {why}")
        sys.exit(1)

    base_ref = os.environ.get("BASE_SHA", "").strip() or "HEAD^"
    head_ref = os.environ.get("HEAD_SHA", "").strip()
    current = get_current_news(head_ref)
    previous = get_news_at_commit(base_ref)
    prev_ids = {i.get("id") for i in previous}
    new_items = [i for i in current if i.get("id") not in prev_ids]

    compare_desc = f"{base_ref} -> {head_ref or '(작업 디렉터리)'}"
    if not new_items:
        notice(f"새로 추가된 소식이 없어(기준 {compare_desc}) 알림을 보내지 않았습니다.")
        return

    # 국내 소식 우선. 예전에는 한 번에 최대 10건만 보내고 나머지는 버렸지만,
    # 지금은 건수 제한 없이 배치(BATCH_SIZE)로 나눠 모두 보냄.
    new_items.sort(key=lambda i: not i.get("isDomestic"))

    sent, fails = 0, []
    for batch_start in range(0, len(new_items), BATCH_SIZE):
        batch = new_items[batch_start:batch_start + BATCH_SIZE]
        for n, item in enumerate(batch):
            ok, why = send_telegram_with_retry(token, chat_id, format_message(item))
            if ok:
                sent += 1
            else:
                fails.append(f"{item.get('id')}: {why}")
            if n < len(batch) - 1:
                time.sleep(SEND_PAUSE_SEC)
        if batch_start + BATCH_SIZE < len(new_items):
            time.sleep(BATCH_PAUSE_SEC)

    if fails:
        error(f"{sent}/{len(new_items)}건 전송, 실패 {len(fails)}건 → " + " | ".join(fails[:5]))
        sys.exit(1)
    notice(f"{sent}/{len(new_items)}건 전송 완료 → {chat_id} (기준 {compare_desc})")


if __name__ == "__main__":
    main()
