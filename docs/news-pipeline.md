# 뉴스 파이프라인 (add-news → fill-images → telegram-notify)

이 문서는 `.github/workflows/{add-news,fill-images,telegram-notify}.yml`과
`scripts/{build.py,fill_images.py,notify_telegram.py}`로 이뤄진 뉴스 자동
게시 파이프라인의 동작 방식, 계약(contract), 그리고 일부러 선택한 제약을
정리합니다. 이 세 워크플로·세 스크립트·`tests/`·본 문서 외의 파일
(`index.html`, `scripts/pages.py`, `README.md` 등)은 이 작업 범위에서
변경하지 않았습니다.

## 전체 흐름

```
incoming/new.json 푸시
        │
        ▼
  add-news.yml  ── 검사 + news.json/rss.xml/sitemap.xml/stats.json/n/*.html 갱신·커밋·푸시
        │                (사진 채우기는 여기서 하지 않음 → 게시가 사진 때문에 늦어지지 않음)
        │
        ├── GitHub Pages 빌드 명시 요청 (requestPagesBuild)
        ├── workflow_dispatch로 fill-images.yml 깨움 (항상)
        └── workflow_dispatch로 telegram-notify.yml 깨움 (새 항목이 1건 이상일 때만,
            base_sha=커밋 직전 SHA, head_sha=push 성공 직후 정확한 SHA를 함께 넘김)
```

`fill-images.yml`은 매일 23:30 UTC(한국시간 08:30) 예약 실행으로도 돌아서,
어떤 이유로든 신호를 놓친 항목도 결국 채워집니다.

## 왜 `GITHUB_TOKEN` push가 아니라 명시적 `workflow_dispatch`인가

GitHub Actions는 `GITHUB_TOKEN`으로 만든 push가 저장소의 다른 `on: push`
워크플로를 **연쇄적으로 트리거하지 않도록** 막아 둡니다(무한 재귀 방지).
`workflow_dispatch`/`repository_dispatch`는 예외로, `GITHUB_TOKEN`으로도
명시적으로 호출하면 항상 실행됩니다. 그래서:

- `add-news.yml`이 봇 계정으로 `news.json`을 커밋·푸시해도 `fill-images.yml`의
  `on: push` 트리거는 사실상 거의 실행되지 않습니다(사람이 직접 `news.json`을
  push하는 드문 경우에만 안전망으로 동작). `telegram-notify.yml`은 아예
  `on: push` 트리거를 두지 않습니다(아래 "텔레그램 트리거는 단일 경로" 참고).
- 대신 `add-news.yml`이 커밋·푸시에 **성공한 뒤** `actions/github-script`로
  `createWorkflowDispatch`를 호출해 두 워크플로를 깨웁니다. 추가 Secret이나
  PAT(개인 액세스 토큰)·GitHub App을 새로 만들 필요가 없습니다(`actions: write`
  권한만 있으면 됨) — 저장소에 별도 `SITE_TOKEN` 같은 Secret이 설정되어 있지
  않음을 확인했고, 새 Secret을 추가하지 않는 범위에서 이 방식을 택했습니다.
- 신호 전송(`continue-on-error: true`)이 실패해도 **이미 끝난 게시 결과에는
  영향이 없습니다**. 다음 날 예약 실행(`fill-images.yml`)이 안전망 역할을 합니다.

## 텔레그램 트리거는 단일 경로입니다 (push 트리거 제거)

`telegram-notify.yml`은 **의도적으로 `on: push` 트리거가 없습니다.**
`workflow_dispatch`(add-news.yml이 보내는 명시적 신호) 하나만이 유일한
트리거입니다.

왜 이렇게 했는지: push 트리거와 명시적 dispatch를 동시에 두면, 봇 커밋은
GITHUB_TOKEN push가 다른 워크플로를 연쇄 트리거하지 않는다는 GitHub 제약
덕분에 거의 중복이 일어나지 않지만, **사람이 `news.json`을 직접 push하는
경우에는 push 트리거가 정상 작동**하므로 그 사람이 다음에 다시 봇 경로로
새 소식을 추가했을 때(add-news.yml의 dispatch)와 겹쳐 두 번 전송될 여지가
있었습니다. concurrency 그룹으로 "동시 실행만" 막는 방식은 이 경우를 막지
못합니다(서로 다른 시점에 실행되는 두 개의 정상적인 트리거이므로). 그래서
직렬화 가정에 기대는 대신 **push 트리거 자체를 없애 가능성을 원천 차단**
했습니다.

**결과적으로 `news.json`을 사람이 직접 고친 경우에는 자동 알림이 오지
않습니다.** 알림이 필요하면 Actions 탭의 `Telegram 새 소식 알림` 워크플로를
`Run workflow`로 직접 실행해야 합니다(`base_sha`를 수정 전 커밋으로 지정하면
더 정확하게 새 id만 골라 보냄; 비워두면 `HEAD^` 기준으로 동작).

## 텍스트 게시는 사진 유무와 무관하게 바로 끝납니다

이전에는 `add-news.yml`이 `fill_images.py`를 동기적으로 실행한 뒤 두 번째
빌드를 돌리고 나서야 커밋했습니다 — 사진 검색(최대 120건 × 요청당 최대
20~25초)이 늦어지면 글 게시 자체가 지연됐습니다. 지금은:

- `add-news.yml`은 `build.py --add` 한 번만 돌리고 바로 커밋·푸시합니다.
- 사진 채우기는 게시 이후 별도 워크플로(`fill-images.yml`)에서 처리합니다.
- `fill-images.yml`은 `FILL_IMAGES_TIME_BUDGET_SEC`(기본 240초)로 실행 시간을
  짧게 묶어 둡니다. 두 워크플로가 `news-write`라는 같은 concurrency 그룹을
  공유해 **동시에 `news.json`을 커밋하는 충돌**은 막되, 그 대신 이미 돌고
  있는 사진 채우기 작업이 있다면 글 게시가 그 작업이 끝날 때까지(최대 몇 분,
  예산 240초 + 빌드/커밋 시간) 대기할 수 있습니다. 이 대기는 **짧게 상한이
  있고**, "사진 때문에 영원히 막힘"과는 다릅니다.
- 못 채운 이미지는 `imageTried` 날짜가 찍혀 다음 예약 실행이나 다음 게시
  직후 신호에서 이어서 처리됩니다(최대 3일 간 재시도). 단, 시간 예산이
  "처리 도중"에 소진되어 끊긴 항목에는 `imageTried`를 남기지 않습니다 —
  실제로 찾아봤지만 못 찾은 것과, 예산이 없어 시도조차 못 한 것을 구분해
  후자는 다음 실행에서 대기 없이 바로 다시 시도합니다.

### 시간 예산은 전체 실행뿐 아니라 요청 하나하나에도 적용됩니다

`FILL_IMAGES_TIME_BUDGET_SEC`는 항목 사이에서만 확인하는 게 아니라, 모든
개별 HTTP 요청(`http_get`)에도 전달됩니다. 요청을 보내기 직전 남은 예산이
0 이하면 네트워크를 아예 열지 않고 `BudgetExceeded` 예외를 던지고, 남은
예산이 있으면 그 요청의 타임아웃을 `min(원래 타임아웃, 남은 예산)`으로
깎습니다. 그래서 전체 실행 시간은 "예산 + 그 순간 진행 중이던 요청 하나의
깎인 타임아웃"만큼만 넘을 수 있고, 그 초과분은 예산에 가까워질수록
0에 수렴합니다(바운드된 아주 짧은 여유). 한 항목을 처리하다가 여러 단계
(원문 읽기 → 우회 → 검색)를 거치며 타임아웃이 누적돼 전체 예산을 크게
넘기던 예전 문제를 막습니다. `BudgetExceeded`는 각 단계의 `except Exception`
블록에서 명시적으로 다시 던져(재전파) "일반 실패"와 섞이지 않게 했습니다.

## 동시성(concurrency)과 충돌 처리

- `add-news.yml`, `fill-images.yml`은 **같은** concurrency 그룹(`news-write`)을
  써서 `news.json` 쓰기 작업이 한 번에 하나만 실행되게 합니다.
- `telegram-notify.yml`은 `news.json`을 쓰지 않고 읽기만 하므로 별도 그룹
  (`telegram-<head_sha 또는 sha>`)을 씁니다. push 트리거가 없으므로 지금은
  거의 발생할 일이 없지만, 사람이 같은 커밋을 대상으로 두 번 수동 실행하는
  경우에 대비한 보조 안전장치일 뿐이며, 중복 방지의 **주 수단은 트리거를
  하나만 남긴 것**입니다(concurrency 직렬화 가정에 기대지 않음).
- 두 워크플로 모두 **force push를 절대 쓰지 않습니다.** `git pull --rebase`가
  네트워크 문제로 실패하면 그대로 재시도하고, **충돌로 실패하면 먼저
  `git rebase --abort`로 깨끗한 상태로 되돌린 뒤에만** 재시도합니다(중단된
  rebase 상태로 재시도를 반복하면 계속 실패하고 저장소가 이상한 상태로 남을
  수 있었음). 5회 재시도 후에도 실패하면 작업을 실패로 표시하고, 기존
  `news.json` 내용은 절대 덮어쓰지 않습니다.

## 텔레그램 알림: 정확한 두 커밋(base_sha, head_sha)으로 고정 비교

`notify_telegram.py`는 "기준 커밋의 news.json"과 "비교 대상 커밋의
news.json"을 id 집합으로 비교해 새 항목만 찾습니다. 두 지점 모두 **정확한
commit SHA로 고정**합니다:

- `base_sha` — `add-news.yml`이 새 항목을 커밋하기 **직전**에 캡처한 SHA.
- `head_sha` — `add-news.yml`이 push에 **성공한 직후**(rebase로 SHA가 바뀔
  수 있으므로 push 성공 후 다시 `git rev-parse HEAD`로 읽음) 캡처한 그
  커밋 SHA.

왜 둘 다 고정해야 하는지: 기준을 단순히 `HEAD^`로, 비교 대상을 "체크아웃한
main의 최신 상태"로 두면 두 가지 문제가 있었습니다.

1. `add-news`가 푸시한 뒤 `fill-images`의 사진 채우기 커밋이 먼저 도착하고
   그다음에 `telegram-notify`가 실행되면, `HEAD^`가 이미 "새 항목이 추가된
   뒤" 상태를 가리키게 되어 새 id를 놓치고 알림을 0건으로 보낼 수 있었습니다.
2. "비교 대상"을 가변적인 main 최신 상태로 두면, `telegram-notify`가 실제로
   실행되는 시점에 main이 이미 더 앞서 나가 있을 경우(사진 채우기 커밋 등)
   그 사이에 끼어든 상태와 뒤섞여 비교 기준이 흔들릴 수 있습니다.

그래서 `notify_telegram.py`는 `BASE_SHA`/`HEAD_SHA` 환경변수가 있으면 **둘 다**
`git show <SHA>:news.json`으로 직접 읽어 비교하고, 체크아웃된 작업 디렉터리
파일은 전혀 읽지 않습니다(`tests/test_notify_telegram.py`의
`test_head_sha_pins_current_to_exact_commit_not_working_tree`가 이를
검증 — 작업 디렉터리를 읽으면 테스트가 실패하도록 함정을 심어 확인).
`HEAD_SHA`가 없으면(사람이 `base_sha`만 주거나 아무것도 안 주고 수동 실행)
현재 작업 디렉터리의 `news.json` 파일로, `BASE_SHA`가 없으면 `HEAD^`로
각각 안전하게 폴백합니다.

## 텔레그램 알림: 건수 제한 없음 + 배치 전송

- 예전에는 새 항목이 10건을 넘으면 나머지를 **조용히 버렸습니다.** 지금은
  건수 제한 없이 전부 보냅니다 — `BATCH_SIZE`(기본 20건)씩 나눠서 배치 사이에
  짧게 쉬고(`BATCH_PAUSE_SEC`), 배치 안에서도 메시지 사이에 짧게 쉬어
  (`SEND_PAUSE_SEC`) 텔레그램 API 속도 제한을 지킵니다.
- 일시적 오류(네트워크 예외, HTTP 429 속도제한, 5xx 서버 오류)만 항목당 최대
  `MAX_TRANSIENT_RETRIES`(2)회 재시도합니다. 400대 요청 오류(잘못된 chat_id
  등)는 같은 결과가 반복될 뿐이므로 재시도하지 않습니다.
- **중복 발송(동일 메시지 재전송)은 하지 않습니다.** 항목마다 전송 함수를
  정확히 한 번만 호출하고, 그 호출 내부에서만 일시적 오류를 재시도합니다.
  이미 성공한 항목을 다시 부르는 바깥쪽 재시도 루프는 없습니다.
- 알려진 한계: 이번 실행에서 일부 항목이 영구 오류로 끝내 실패하면, 그 항목은
  이미 `news.json`에 들어 있으므로(새 id로 다시 집계되지 않음) 다음 실행에서도
  재전송되지 않습니다. 재전송이 필요하면 `workflow_dispatch`로 수동 실행하며
  `base_sha`를 그 항목이 추가되기 전 커밋으로 지정해야 합니다.

## 새로 들어오는 소식(incoming/new.json) 검사 계약

`summary`/스펙 내용이 사실인지는 정규식으로 판정할 수 없습니다(의미 검증
불가). 그래서 `scripts/build.py`는 **과거 128건 기록에는 적용하지 않는**,
새로 들어오는 항목 전용 검사(`validate_incoming`)로 "출처 확인 책임"을
생산자(수집 에이전트/제보자)에게 명시적으로 지웁니다.

`incoming/new.json`의 각 항목은 기존 `REQUIRED` 필드(`date`, `company`,
`brand`, `type`, `summary`, `link`, `category`)에 더해:

1. `link`가 **https://로 시작하는 절대 URL**이어야 함 (과거 기록은 `http`도
   허용되는 일반 검사만 받음 — 하위 호환, 재검사 없음).
   예외: https를 지원하지 않는 사이트는 `scripts/build.py`의
   `HTTP_ALLOWED_DOMAINS`에 있는 도메인만 `http://`를 허용함
   (현재 `ntusys.com`, `www.ntusys.com` — 엔티유시스템즈). 다른 도메인의 `http://`,
   하위 도메인 등 목록에 없는 호스트는 그대로 거부됨.
2. `productName` 또는 `evidence`(원문 근거·인용) 중 **적어도 하나**는
   비어 있지 않아야 함.

조건을 만족하지 못하면:

- **조용히 통과시키지 않고** 해당 항목만 명확한 사유와 함께 거부합니다
  (예: `ExampleBrand — https://...: productName 또는 evidence(원문 근거) 중
  하나는 있어야 함`).
- `python3 scripts/build.py --add incoming/new.json`은 종료 코드 1로
  실패하고, **news.json 파일은 전혀 바뀌지 않습니다**(부분 저장 없음).
- GitHub Actions 로그에 사유가 그대로 출력되므로, 어떤 항목이 왜 막혔는지
  바로 확인할 수 있습니다.
- 이미 저장된 과거 기록은 이 기준으로 재검사되거나 무효화되지 않습니다.

`evidence` 필드는 선택 필드로 스키마에 추가된 것이며, 기존 128건 레코드의
구조를 바꾸지 않습니다(`AGENTS.md`의 "news.json 스키마 임의 변경 금지" 규칙
준수 — 추가는 항목별 선택 필드일 뿐 기존 구조를 바꾸지 않음).

## 이미지 채우기: "근거 없으면 사진 없음" (og:image 포함)

- **원문 기사의 대표 이미지(`og:image` 등)도 더 이상 무조건 신뢰하지
  않습니다.** 예전에는 "기사 자체가 근거"라고 보고 og:image를 그대로
  받아들였지만, 여러 제품을 묶어 소개하는 기사나 사이트 공통 로고/배너가
  og:image로 잡히면 엉뚱한 제품 사진이 붙을 수 있었습니다. 지금은 og:image도
  이미지 주소(경로·쿼리) 안에 **이 소식의 제품명 단어가 실제로 있어야만**
  채택합니다. 제품명을 전혀 모르면(`productName` 없음) og:image도 검색도
  아예 시도하지 않습니다 — "근거 없으면 사진 없음" 정책을 og:image에도
  동일하게 적용한 것입니다. 유일한 예외는 유튜브 영상 썸네일로, 기사가 직접
  담고 있는 고유 영상 ID에서 뽑은 것이라 다른 제품과 섞일 위험이 없습니다.
- 검색(Google/DuckDuckGo/Bing)으로 이미지를 찾는 4단계도 **제품명 단서가
  있을 때만** 시도합니다.
- 예전에는 제품명 기반 검색이 실패하면 "브랜드명 + audio"로 다시 검색해
  **그 브랜드의 아무 대표 사진**을 붙이는 폴백이 있었습니다. 기사/제품과
  무관한 사진이 붙을 위험이 커서 **제거했습니다.**
- 기사 본문 사진도 제품명 단어가 파일명/대체텍스트에 실제로 있는 것만
  채택합니다(브랜드명만 일치하는 본문 사진은 더 이상 허용하지 않음).
- **사람이 직접 확인해 넣은 사진은 절대 덮어쓰지 않습니다.** `imageUrl`이
  있거나 `imageSource`가 `"manual"`인 항목은 자동화가 건드리지 않습니다.

## GitHub Pages 빌드를 명시적으로 요청합니다

GitHub 공식 문서는 다음을 명시합니다: *"Commits pushed by a GitHub Actions
workflow that uses the GITHUB_TOKEN do not trigger a GitHub Pages build."*
즉 `add-news.yml`/`fill-images.yml`이 봇 계정으로 커밋·푸시해도 **Pages
빌드가 자동으로 일어나지 않습니다.** 이 저장소의 Pages 설정은 "Deploy from a
branch"(main, 루트) — 레거시 빌드 방식이며, 이 설정 자체는 바꾸지 않았습니다.

그래서 두 워크플로 모두 push에 성공한 뒤 REST API
`POST /repos/{owner}/{repo}/pages/builds`(`github.rest.repos.requestPagesBuild`,
공식 문서 `docs.github.com/en/rest/pages/pages` "Request a GitHub Pages
build")를 명시적으로 호출해 빌드를 요청합니다. 이 엔드포인트는 "최신 기본
브랜치에서 빌드해 달라"는 요청으로, 소스/설정을 바꾸지 않고 수동 push와
같은 효과만 냅니다. 필요한 권한은 `permissions.pages: write`뿐입니다.

- 이 단계는 `continue-on-error: true`로 감싸 **실패해도 이미 끝난 게시
  결과(커밋·푸시)에는 영향을 주지 않습니다.**
- 단, 호출이 실패하면 `core.setFailed`로 그 스텝 자체는 명확히 "실패"로
  표시됩니다(조용히 성공한 것처럼 넘어가지 않음) — Actions 실행 목록에서
  빨간 X로 바로 보이므로 원인을 확인할 수 있습니다.
- 알려진 제약: 이 엔드포인트는 "legacy" 빌드 방식(Deploy from a branch)
  전용입니다. 저장소 Pages 설정이 나중에 "GitHub Actions로 배포"(workflow
  빌드 방식)로 바뀌면 이 호출은 더 이상 유효하지 않으며, 별도 배포 워크플로
  (`actions/deploy-pages` 등)로 교체해야 합니다. 실제 배포 완료 여부까지는
  이 스텝이 보장하지 않습니다(빌드 "요청"이 접수됐는지까지만 확인) — 배포
  완료 확인이 필요하면 `GET /repos/{owner}/{repo}/pages/builds/latest`를
  별도로 폴링해야 합니다(이번 범위에서는 구현하지 않음).

## 테스트

`tests/`의 모든 테스트는 오프라인입니다 — 실제 네트워크 전송·요청이나
텔레그램/SerpApi/GitHub API 자격증명을 쓰지 않고, 모두 가짜(mock) 응답과
작은 fixture 데이터로 검사합니다. 실행:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

- `tests/test_build.py`: incoming 검사(https/evidence 계약), 원문 링크
  중복·id 충돌 방지, 검사 실패 시 news.json 불변(subprocess로 실제
  `build.py --add` CLI를 돌려 확인).
- `tests/test_fill_images.py`: 로고/배너·다른 모델을 가리키는 og:image 거부,
  제품명 단서 없을 때 검색·og:image 모두 시도하지 않음, `imageSource: manual`
  보호, 시간 예산이 개별 HTTP 요청에도 전파되는지(타임아웃이 남은 예산으로
  깎이는지, 예산 소진 시 요청 자체를 시도하지 않는지), 예산 중단 항목에
  `imageTried` 마크가 남지 않는지.
- `tests/test_notify_telegram.py`: 새 항목 11건이 10건에서 잘리지 않고 모두
  배치로 전송됨, 일시적 오류만 제한된 횟수로 재시도(중복 발송 없음),
  `base_sha`/`head_sha` 둘 다로 정확한 두 커밋을 고정 비교(작업 디렉터리를
  전혀 읽지 않음을 함정 테스트로 확인), 중간에 더 나아간 main 상태와
  섞이지 않음.

## 이번 변경 범위와 의도적으로 다루지 않은 것

- 변경: `.github/workflows/{add-news,fill-images,telegram-notify}.yml`,
  `scripts/{build.py,fill_images.py,notify_telegram.py}`, `tests/*`, 본 문서.
- 바꾸지 않음: `index.html`, `scripts/pages.py`, `README.md` (다른 작업자가
  담당하는 명명/표시 로직), `news.json`의 기존 128건 데이터·스키마
  (스크립트 동작만 고쳤고 데이터는 건드리지 않음), GitHub Pages 소스/설정
  ("Deploy from a branch"를 그대로 유지, 빌드만 명시적으로 요청).
- "사이트 관리센터"로 불리는 별도 관리 설정(Google Apps Script 기반, 이번
  작업 범위에서 소스 코드를 확인할 수 없었음)과 경쟁하는 설정 소스를 새로
  만들지 않았습니다. 이 파이프라인은 `incoming/new.json` → `news.json`
  경로만 다루며, 회사/뉴스 데이터를 관리하는 별도 체계를 대체하거나
  우회하지 않습니다.
- 매거진 리디자인 등 레이아웃/디자인 변경은 포함되지 않았습니다.
- 라이브 환경에서 `requestPagesBuild` 호출이 실제로 202/201을 받고 배포까지
  이어지는지는 머지·실행 전까지 100% 보장할 수 없습니다(공식 문서와 현재
  Pages 설정 확인까지만 이번 범위에서 검증). 실제 실행 로그로 최종 확인이
  필요합니다.

## 새 소식 멈춤 점검 (stall-check.yml, 2026-10 추가)

- 새 소식 수집은 이 저장소 밖의 예약 작업이 `incoming/new.json`을 올려야 시작됩니다. 그 작업이
  멈추면 Actions에는 실패가 남지 않고(아무것도 실행되지 않으므로) 사진 채우기 커밋만 계속 생깁니다.
- `.github/workflows/stall-check.yml`이 매일 10:00(한국) `scripts/check_stall.py`를 실행해
  "가장 큰 id가 처음 들어온 커밋 시각"을 마지막 새 소식 시각으로 보고, 48시간이 넘으면
  `[자동 점검] 새 소식 …` 이슈를 엽니다(이미 열려 있으면 새로 열지 않음). 새 소식이 다시 들어오면
  이슈에 댓글을 남기고 자동으로 닫습니다.
- 텔레그램 알림은 Secret `TELEGRAM_ALERT_CHAT_ID`(운영자 개인 대화방 id)가 있을 때만 보냅니다.
  `TELEGRAM_CHAT_ID`는 구독자용 공개 채널이므로 점검 알림에 쓰지 않습니다.
- 테스트: `tests/test_check_stall.py` (오프라인).
