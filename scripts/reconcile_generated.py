#!/usr/bin/env python3
"""rebase 충돌 중 "생성 파일만" 안전하게 재생성하는 복구 스크립트.

배경 (fill-images.yml 신뢰성 수정):
  대기열에 밀려 있던 fill-images 실행이 오래된(트리거 당시) SHA를 체크아웃한
  상태에서 사진을 채우고 커밋을 시도했는데, 그 사이 다른 실행(수동 재실행 등)이
  이미 더 새 stats.json을 포함한 커밋을 origin/main에 올려 둔 적이 있었습니다.
  `git pull --rebase origin main`이 stats.json에서 충돌을 내며 실패했고,
  기존 재시도 루프는 매번 `git rebase --abort` 후 똑같은 상태로 다시 시도해
  5번 모두 동일하게 실패했습니다(사진은 처리됐지만 아무것도 반영되지 못함).

이 스크립트가 다루는 범위는 build.py/pages.py가 news.json만으로 100%
재계산하는 "순수" 생성 파일(GENERATED_TOP ∪ n/*.html)뿐입니다:
  stats.json, rss.xml, sitemap.xml, n/*.html

index.html은 **의도적으로 제외**합니다. AGENTS.md는 index.html도 "생성
파일"로 분류하지만, 실제로는 정적 뼈대(헤더/CSS/구조)와 PRERENDER·
COUPANG_PICKS 주입 구간이 한 파일에 섞여 있습니다. 이 파일이 rebase
충돌 목록에 떴다는 것은 git이 자동 병합에 실패했다는 뜻이고, 충돌이
주입 구간 안에만 있는지 정적 뼈대(사람이 직접 고친 부분)에도 걸쳐
있는지를 안전하게 구분할 방법이 없습니다. 주입 구간만 다시 써 넣으면
뼈대 쪽에 남은 git 충돌 표시(<<<<<<< 등)를 못 보고 "해결됨"으로 커밋할
위험이 있으므로, index.html이 충돌 목록에 있으면 무조건 other로 분류해
자동 해결을 포기하고 실패시킵니다(원본 보호 우선).

(index.html 자체가 충돌하지 않은 "평범한" 경우에는 여전히 regenerate()가
build_pages()를 통해 다시 계산해 둡니다 — news.json이 바뀌었으니 당연히
최신 상태로 맞춰야 하고, 이건 git 충돌 해결이 아니라 일반적인 재빌드일
뿐이라 안전합니다. 그래도 그 전에 index.html에 남은 git 충돌 표시가
없는지 한 번 더 확인합니다 — 아래 "충돌 표시 가드" 참고.)

충돌 표시 가드(conflict marker guard): classify()가 "생성 파일만 충돌"로
판단해 통과시켜도, regenerate()는 실제로 쓰기 전에 news.json과
index.html 본문에 미해결 git 충돌 표시(<<<<<<<, =======, >>>>>>>)가
남아 있는지 다시 한번 직접 검사합니다. 호출 경로가 바뀌거나(classify를
거치지 않고 regenerate가 직접 불리는 경우 등) 충돌 목록이 실제 상태와
어긋나는 예외적 상황에서도, 깨진 파일을 "정상"으로 오인해 그 내용을
기준으로 재계산·커밋하는 일을 막기 위한 2차 방어선입니다.

왜 안전한가: 이 파일들은 같은 news.json이면 항상 같은 출력이 나오는 순수
함수 결과물입니다. rebase 도중 news.json 자체가 충돌 없이 합쳐졌다면(=
git이 이미 두 쪽의 내용을 성공적으로 병합해 작업 디렉터리에 반영했다면),
병합된 news.json을 다시 build.py에 통과시키는 것만으로 두 쪽이 각자
시점에 독립적으로 만든 파생 파일 차이(예: stats.json의 generated_at
타임스탬프, 그 사이에 반영된 통계 수치)를 매번 새로 계산한 "정답"으로
되돌릴 수 있습니다 — 어느 한쪽 커밋의 내용을 임의로 골라 쓰는 게
아닙니다.

이 스크립트는 news.json이나 다른 원본/수동 파일(coupang_picks.html 등)의
충돌은 **절대** 다루지 않습니다: GENERATED_TOP/GENERATED_DIR 밖의 충돌
경로가 하나라도 있으면 아무 파일도 건드리지 않고 0이 아닌 코드로
종료합니다 — 호출자(fill-images.yml)는 이 경우 rebase를 중단하고 "명확히
한 번" 실패 처리해야 하며, 고쳐지지 않는 내용 충돌을 5번 똑같이 반복
재시도해서는 안 됩니다.

사용법 (워크플로 안에서, rebase가 충돌로 실패한 직후):
  python3 scripts/reconcile_generated.py
  종료 코드:
    0 — 충돌이 전부 생성 파일 안에만 있었고, 재생성·git add까지 끝남
        (호출자는 이어서 `git rebase --continue`를 실행하면 됨)
    0 — 애초에 충돌 파일이 없었음(아무 것도 하지 않음, 안전하게 성공 처리)
    2 — 생성 파일이 아닌 경로가 충돌에 섞여 있음 (news.json 등) → 자동으로
        고치지 않음. 호출자는 즉시 rebase --abort 후 실패 처리해야 함
    3 — 충돌 파일 목록을 읽지 못함(git 호출 실패 등)
    4 — 재생성 자체가 실패함(news.json이 손상돼 보이는 등)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build  # noqa: E402
from pages import build_pages  # noqa: E402

ROOT = SCRIPTS_DIR.parent

# 자동 재생성 허용 목록: news.json만으로 100% 결정되는 "순수" 파생 파일만.
# index.html은 의도적으로 제외(위 모듈 docstring 참고). news.json, incoming/*,
# coupang_picks.html, docs/* 같은 원본·수동 파일도 당연히 포함하지 않음.
GENERATED_TOP = {"stats.json", "rss.xml", "sitemap.xml"}
GENERATED_DIR = "n"  # stage()가 n/ 디렉터리 통째로 git add할 때만 쓰는 보조 상수

# n/ 바로 아래의 .html 파일만 허용(n/news-5.html 유형). n/에 중첩된 경로
# (n/sub/x.html)나 .html이 아닌 파일(n/foo.txt), 디렉터리 자체(n)는 일부러
# 제외함 — pages.py가 실제로 쓰는 것은 이 패턴뿐이고, 그 외 경로가 충돌에
# 있다면 예상치 못한 상황(예: 스크립트 버그, 수동 파일 중간 저장 등)일 수
# 있으므로 자동 재생성 대상에서 제외해 안전한 쪽으로 판단함.
_N_HTML_RE = re.compile(r"^n/[^/]+\.html$")

# 미해결 git 충돌 표시(표준 3줄 형식). 줄 시작에서만 찾아 오탐지 가능성을 줄임.
_CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def is_generated_path(rel_path):
    """git이 돌려주는 경로(예: 'n/news-5.html', 'stats.json')가 재생성으로
    안전하게 복구 가능한 "순수" 생성 파일인지 판단 (index.html은 제외)."""
    rel_path = str(rel_path).strip().replace("\\", "/")
    if rel_path in GENERATED_TOP:
        return True
    return bool(_N_HTML_RE.match(rel_path))


def has_conflict_markers(text):
    """미해결 git 충돌 표시(<<<<<<< 등, 줄 시작)가 남아 있는지 검사."""
    return any(line.startswith(m) for line in text.splitlines() for m in _CONFLICT_MARKERS)


def classify(paths):
    """충돌 경로 목록을 (생성 파일만, 그 외) 두 리스트로 나눔. 순서는 보존."""
    generated, other = [], []
    for p in paths:
        p = str(p).strip()
        if not p:
            continue
        (generated if is_generated_path(p) else other).append(p)
    return generated, other


def list_conflicted_files(root):
    """현재 git 작업 디렉터리에서 rebase 충돌(unmerged) 상태인 파일 경로 목록.
    git 호출 자체가 실패하면 예외를 던짐(호출자가 안전하게 실패 처리하도록;
    "충돌 없음"과 "충돌 목록을 못 읽음"을 절대 같은 것으로 취급하지 않음)."""
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def regenerate(root):
    """작업 디렉터리의 news.json으로부터 파생 파일(rss/sitemap/index/n/stats)을
    전부 다시 계산해 디스크에 씀. news.json 자체는 읽기만 하고 절대 쓰지 않음.

    merge된 news.json이 build.py의 일반 검사(validate)조차 통과하지 못하면
    (예: 병합 결과가 실제로 손상됨) 아무 파일도 건드리지 않고 예외를 던짐 —
    "생성 파일만 충돌"이라는 전제가 깨진 것이므로 조용히 밀어붙이지 않음.

    2차 방어선: news.json과 index.html에 미해결 git 충돌 표시가 남아
    있으면(호출자가 classify()를 거치지 않고 잘못 불렀거나, 예상치 못한 상황으로
    그 사이 index.html이 다른 충돌에 휘말려 들어간 경우 등) 정상으로 오인해 그 내용을
    기준으로 재계산·커밋하지 않도록 즉시 중단함."""
    path = root / "news.json"
    news_text = path.read_text(encoding="utf-8")
    if has_conflict_markers(news_text):
        raise RuntimeError(
            "news.json에 미해결 git 충돌 표시(<<<<<<< 등)가 남아 있음 — 재생성을 중단함"
        )
    index_path = root / "index.html"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        if has_conflict_markers(index_text):
            raise RuntimeError(
                "index.html에 미해결 git 충돌 표시(<<<<<<< 등)가 남아 있음 — 재생성을 중단함 "
                "(index.html은 생성 전용 파일이 아니므로 덮어쓰기 전 항상 검사)"
            )
    items = json.loads(news_text)
    errors = build.validate(items)
    if errors:
        raise RuntimeError(
            "news.json 검사 실패 — 재생성을 중단함(merge된 news.json 자체가 "
            "손상됐을 수 있어 수동 확인 필요): " + "; ".join(errors[:5])
        )
    (root / "rss.xml").write_text(build.build_rss(items), encoding="utf-8")
    build_pages(root, items, build.pub)
    stats = build.compute_stats(items)
    (root / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return items


def stage(root):
    """재생성한 파일만 git add (news.json·coupang_picks.html 등은 절대 건드리지 않음)."""
    subprocess.run(
        ["git", "-C", str(root), "add", "-A", "--",
         "stats.json", "rss.xml", "sitemap.xml", "index.html", GENERATED_DIR],
        check=True,
    )


def reconcile(root, conflicted_paths):
    """classify → (생성 파일만이면) regenerate + stage까지 한 번에 수행하는
    순수 오케스트레이션 함수 (git 충돌 목록을 직접 읽지 않고 인자로 받음 —
    테스트에서 git 없이도 호출 가능하게 하기 위함). main()과 테스트가 함께 씀.

    돌려주는 값: (generated, other, items)
      - other가 비어 있지 않으면: 생성 파일이 아닌 충돌이 섞여 있어 아무 것도
        건드리지 않았음 (items는 None).
      - conflicted_paths가 비어 있으면: 할 일이 없어 아무 것도 건드리지 않음
        (items는 None).
      - 그 외(생성 파일만 충돌): regenerate 성공 시 items는 재계산된
        news.json 항목 리스트. regenerate가 news.json 손상 등으로 실패하면
        예외가 그대로 전파됨(호출자가 처리)."""
    generated, other = classify(conflicted_paths)
    if other or not conflicted_paths:
        return generated, other, None
    items = regenerate(root)
    stage(root)
    return generated, other, items


def main():
    try:
        conflicts = list_conflicted_files(ROOT)
    except Exception as e:  # git 호출 자체 실패
        print(f"::error::git 충돌 목록을 읽지 못함: {e}", file=sys.stderr)
        return 3

    if not conflicts:
        print("충돌 파일 없음 — 재생성할 필요 없음 (아무 것도 하지 않고 성공 처리)")
        return 0

    try:
        generated, other, items = reconcile(ROOT, conflicts)
    except Exception as e:
        print(f"::error::재생성 실패: {e}", file=sys.stderr)
        return 4

    if other:
        print(
            "::error::생성 파일이 아닌 충돌이 섞여 있음(news.json 등 원본 포함 가능) — "
            "자동으로 고치지 않음: " + ", ".join(other),
            file=sys.stderr,
        )
        return 2

    print(f"생성 파일 전용 충돌 확인됨 ({len(generated)}건): " + ", ".join(generated))
    print(f"재생성 완료: news.json {len(items)}건 기준으로 stats/rss/sitemap/index/n을 "
          "다시 계산해 스테이징함 (news.json 자체는 건드리지 않음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
