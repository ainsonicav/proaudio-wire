#!/usr/bin/env python3
"""새 소식이 멈췄는지(48시간 이상 추가 없음) 점검하고 운영자에게 알립니다.

GitHub Actions(.github/workflows/stall-check.yml)에서 하루 한 번 실행됩니다.

판단 기준: news.json의 가장 큰 id(news-N)가 '처음 들어온 커밋' 시각 = 마지막으로 새 소식이
추가된 시각. (게시일 칸에는 행사 날짜가 들어가는 경우가 있어 날짜 대신 git 기록을 씁니다.
사진 채우기 커밋은 id를 늘리지 않으므로 '업데이트'로 세지 않습니다.)

알림:
  - GitHub 이슈: 멈춤이면 '[자동 점검] 새 소식 …' 이슈를 엽니다(이미 열려 있으면 새로 열지 않음).
    다시 새 소식이 들어오면 그 이슈에 댓글을 남기고 닫습니다. 저장소 주인에게 GitHub 메일 알림이 갑니다.
  - 텔레그램(선택): Secret TELEGRAM_ALERT_CHAT_ID(운영자 개인 대화방 id)가 있을 때만 TELEGRAM_BOT_TOKEN으로
    보냅니다. 구독자용 공개 채널(TELEGRAM_CHAT_ID, @proaudiowire)에는 절대 보내지 않습니다.

환경 변수: GITHUB_TOKEN, GITHUB_REPOSITORY (Actions가 넣어 줌), STALL_HOURS(기본 48),
          TELEGRAM_BOT_TOKEN, TELEGRAM_ALERT_CHAT_ID (선택)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISSUE_TITLE_PREFIX = "[자동 점검] 새 소식"
SITE_URL = "https://news.ainsonic.com"


def max_id(items):
    best = -1
    for it in items if isinstance(items, list) else []:
        m = re.search(r"(\d+)$", str(it.get("id", ""))) if isinstance(it, dict) else None
        if m:
            best = max(best, int(m.group(1)))
    return best


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def news_at(commit):
    try:
        return json.loads(git("show", f"{commit}:news.json"))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def last_added(commits, load):
    """commits: news.json을 바꾼 커밋 [(sha, unix_time), ...] 최신순. load(sha) → 그 시점 news.json.
    현재 최대 id가 처음 나타난 커밋의 (sha, 시각, 최대 id)를 돌려줌."""
    if not commits:
        return None
    current = max_id(load(commits[0][0]))
    found = commits[0]
    for sha, ts in commits[1:]:
        if max_id(load(sha)) < current:
            break
        found = (sha, ts)
    return found[0], found[1], current


def gh_api(method, path, token, body=None):
    url = "https://api.github.com" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "proaudio-wire-stall-check"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or "null")


def send_telegram(token, chat_id, text):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"::warning title=멈춤 점검::텔레그램 전송 실패: {e}")
        return False


def kst(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + 9 * 3600)) + " (한국시간)"


def main():
    hours_limit = float(os.environ.get("STALL_HOURS", "48"))
    log = git("log", "--format=%H %ct", "--", "news.json").split("\n")
    commits = [(l.split()[0], int(l.split()[1])) for l in log if l.strip()]
    info = last_added(commits, news_at)
    if not info:
        print("::error title=멈춤 점검::news.json 기록을 읽지 못했습니다")
        return 1
    sha, ts, mid = info
    age_h = (time.time() - ts) / 3600
    stalled = age_h >= hours_limit
    summary = f"마지막 새 소식: news-{mid}, {kst(ts)} 추가 ({age_h:.0f}시간 전, 커밋 {sha[:7]})"
    print(f"::notice title=멈춤 점검::{summary}")

    token, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("GITHUB_TOKEN/GITHUB_REPOSITORY 없음 — 알림 없이 점검 결과만 출력합니다.")
        return 0
    issues = gh_api("GET", f"/repos/{repo}/issues?state=open&per_page=50", token) or []
    open_issue = next((i for i in issues if "pull_request" not in i and i.get("title", "").startswith(ISSUE_TITLE_PREFIX)), None)

    if stalled and not open_issue:
        days = age_h / 24
        body = (f"{summary}\n\n새 소식이 {hours_limit:.0f}시간 넘게 추가되지 않았습니다 (약 {days:.1f}일).\n\n"
                "확인할 것:\n"
                "1. 새 소식을 모아 `incoming/new.json`으로 올리는 자동 수집 작업(저장소 밖에서 예약 실행되는 작업)이 "
                "멈추지 않았는지 — 마지막 실행 기록과 오류를 확인하세요.\n"
                "2. Actions 탭의 '새 소식 추가' 워크플로가 실패하지 않았는지.\n"
                f"3. 사이트: {SITE_URL}/\n\n"
                "새 소식이 다시 들어오면 이 이슈는 자동으로 닫힙니다.")
        created = gh_api("POST", f"/repos/{repo}/issues", token, {"title": f"{ISSUE_TITLE_PREFIX} {days:.0f}일째 없음 (자동 점검)", "body": body})
        print(f"::warning title=멈춤 점검::이슈를 열었습니다: {created.get('html_url')}")
        tg_token, tg_chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
        if tg_token and tg_chat:
            send_telegram(tg_token, tg_chat, f"[프로오디오뉴스 점검] 새 소식이 {days:.0f}일째 없습니다.\n{summary}\n{created.get('html_url', '')}")
        else:
            print("TELEGRAM_ALERT_CHAT_ID가 없어 텔레그램 알림은 건너뜁니다(공개 채널로는 보내지 않음).")
    elif stalled:
        print(f"이미 열린 점검 이슈가 있습니다: {open_issue.get('html_url')}")
    elif open_issue:
        gh_api("POST", f"/repos/{repo}/issues/{open_issue['number']}/comments", token, {"body": f"새 소식이 다시 들어왔습니다. {summary}"})
        gh_api("PATCH", f"/repos/{repo}/issues/{open_issue['number']}", token, {"state": "closed"})
        print("새 소식이 다시 들어와 점검 이슈를 닫았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
