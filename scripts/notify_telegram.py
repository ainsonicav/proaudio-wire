#!/usr/bin/env python3
"""news.json에 새로 추가된 항목만 골라 텔레그램 채널로 보냅니다.

GitHub Actions에서만 실행됩니다 (텔레그램 API는 자동화 환경에서 접속이
막혀 있어, GitHub 서버가 대신 보냅니다).

필요한 저장소 Secret (Settings > Secrets and variables > Actions > Secrets):
  TELEGRAM_BOT_TOKEN  - BotFather가 준 봇 토큰
  TELEGRAM_CHAT_ID    - 채널 사용자명, 예: @proaudiowire

동작:
  - 기본: 이번 커밋과 직전 커밋의 news.json을 비교해 새 id만 전송
  - TEST_MESSAGE=1 : 새 소식과 상관없이 "연결 테스트" 메시지 1건 전송

결과는 GitHub Actions 요약(annotation)에 남고, 설정 누락·전송 실패 시
작업을 실패로 표시합니다(원인 확인용).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = "https://news.ainsonic.com"


def notice(msg):
    print(f"::notice title=텔레그램 알림::{msg}", flush=True)


def error(msg):
    print(f"::error title=텔레그램 알림::{msg}", flush=True)


def load_json_text(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


def get_previous_news():
    """직전 커밋의 news.json 내용. 없으면 빈 리스트."""
    try:
        out = subprocess.run(
            ["git", "show", "HEAD^:news.json"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return load_json_text(out.stdout)
    except subprocess.CalledProcessError:
        return []


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


def send_telegram(token, chat_id, text):
    """성공하면 (True, ''), 실패하면 (False, 텔레그램이 알려준 이유)."""
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
            return (True, "") if body.get("ok") else (False, body.get("description", str(body)))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return False, f"HTTP {e.code}: {body.get('description', '')}"
        except Exception:  # noqa: BLE001
            return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"요청 오류: {e}"


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
        ok, why = send_telegram(
            token, chat_id,
            "✅ <b>PRO AUDIO WIRE 연결 테스트</b>\n\n이 메시지가 보이면 새 소식 자동 알림이 정상 연결된 것입니다.\n"
            f'<a href="{SITE_URL}">news.ainsonic.com</a>',
        )
        if ok:
            notice(f"연결 테스트 메시지 전송 성공 → {chat_id}")
            return
        error(f"연결 테스트 전송 실패 ({chat_id}): {why}")
        sys.exit(1)

    current = json.load(open(os.path.join(ROOT, "news.json"), encoding="utf-8"))
    previous = get_previous_news()
    prev_ids = {i.get("id") for i in previous}
    new_items = [i for i in current if i.get("id") not in prev_ids]

    if not new_items:
        notice("새로 추가된 소식이 없어 알림을 보내지 않았습니다.")
        return

    # 국내 소식 우선, 한 번에 최대 10건
    new_items.sort(key=lambda i: not i.get("isDomestic"))
    new_items = new_items[:10]

    sent, fails = 0, []
    for item in new_items:
        ok, why = send_telegram(token, chat_id, format_message(item))
        if ok:
            sent += 1
        else:
            fails.append(f"{item.get('id')}: {why}")

    if fails:
        error(f"{sent}/{len(new_items)}건 전송, 실패 {len(fails)}건 → " + " | ".join(fails[:3]))
        sys.exit(1)
    notice(f"{sent}건 전송 완료 → {chat_id}")


if __name__ == "__main__":
    main()
