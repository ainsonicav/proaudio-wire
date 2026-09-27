#!/usr/bin/env python3
"""news.json에 새로 추가된 항목만 골라 텔레그램 채널로 보냅니다.

GitHub Actions에서만 실행됩니다 (텔레그램 API는 이 저장소의 로컬/자동화
환경에서는 접속이 막혀 있어, GitHub 서버가 대신 보냅니다).

필요한 환경변수:
  TELEGRAM_BOT_TOKEN  - 저장소 Secret (Settings > Secrets and variables > Actions)
  TELEGRAM_CHAT_ID    - 채널 사용자명, 예: @proaudiowire (Secret 또는 Variable)

새 항목 판단 방법: 이번 커밋의 news.json과 바로 이전 커밋의 news.json을
비교해서, id가 새로 등장한 항목만 "새 소식"으로 봅니다. 우리 자동화는 항상
새 항목을 배열 맨 앞에 추가하므로 이 방식이 안전합니다.
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = "https://news.ainsonic.com"


def load_json_text(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


def get_previous_news():
    """직전 커밋의 news.json 내용을 가져옵니다. 없으면 빈 리스트."""
    try:
        out = subprocess.run(
            ["git", "show", "HEAD^:news.json"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return load_json_text(out.stdout)
    except subprocess.CalledProcessError:
        return []


def escape_html(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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
        parts.append(f'<a href="{link}">원문 보기</a>')
    return "\n\n".join(parts)


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            if not body.get("ok"):
                print(f"::warning::텔레그램 전송 실패: {body}", file=sys.stderr)
                return False
            return True
    except Exception as e:  # noqa: BLE001
        print(f"::warning::텔레그램 요청 오류: {e}", file=sys.stderr)
        return False


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않아 건너뜁니다.")
        return

    current = json.load(open(os.path.join(ROOT, "news.json"), encoding="utf-8"))
    previous = get_previous_news()

    prev_ids = {i.get("id") for i in previous}
    new_items = [i for i in current if i.get("id") not in prev_ids]

    if not new_items:
        print("새로 추가된 소식이 없어 알림을 보내지 않습니다.")
        return

    # 국내 소식 우선, 최대 10건까지만 (한 번에 너무 많이 쏟아지지 않도록)
    new_items.sort(key=lambda i: not i.get("isDomestic"))
    new_items = new_items[:10]

    sent = 0
    for item in new_items:
        if send_telegram(token, chat_id, format_message(item)):
            sent += 1

    print(f"{sent}/{len(new_items)}건 전송 완료. 사이트: {SITE_URL}")


if __name__ == "__main__":
    main()
