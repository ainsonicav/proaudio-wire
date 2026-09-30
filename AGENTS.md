# PRO AUDIO WIRE - AGENTS.md

이 저장소(https://news.ainsonic.com)는 GitHub Pages를 통해 배포되는 프로오디오 및 관련 장비 뉴스 정적 사이트입니다.

## 폴더/파일 구조

*   `news.json`: 모든 뉴스/소식의 **원본 데이터 파일**입니다.
*   `notices.json`: 공지사항 원본 데이터 파일입니다.
*   `scripts/build.py`, `scripts/pages.py`: 데이터(`news.json`, `notices.json`)를 읽고 조합하여 정적 파일들을 생성하는 Python 스크립트입니다.
*   `index.html`: 메인 페이지입니다. `build.py` 스크립트를 통해 일부 내용(PRERENDER 구간)이 자동으로 생성 및 주입됩니다.
*   `n/`: 개별 뉴스 페이지 HTML 파일들이 위치하는 폴더입니다. `build.py`가 생성합니다.
*   `rss.xml`: RSS 피드 파일입니다. `build.py`가 생성합니다.
*   `sitemap.xml`: 사이트맵 파일입니다. `build.py`가 생성합니다.
*   `stats.json`: 주간 브랜드 및 분야 비율 통계 데이터입니다. `build.py`가 생성합니다.
*   `coupang_picks.html`: 광고/추천 상품(쿠팡 파트너스 등) 위젯 등과 관련된 사이드 레일 HTML 내용을 담고 있는 별도 문서입니다.

## 빌드/실행 명령

파일을 변경하거나 확인하기 위해서는 아래의 명령어를 실행합니다. 파이썬 버전은 **3.11 이상**을 사용해야 합니다.

```bash
python3 scripts/build.py
```

명령을 실행하면 `news.json`을 읽고 검사한 뒤 `index.html`(일부 렌더링 영역), `n/*.html`, `rss.xml`, `sitemap.xml`, `stats.json` 파일이 업데이트되거나 새로 생성됩니다.

## 규칙

1.  **생성 파일 직접 수정 금지**: `index.html`, `n/*`, `rss.xml`, `sitemap.xml`, `stats.json` 등은 스크립트에 의해 자동 생성되므로 **절대 직접 수정하지 마십시오.** 변경이 필요하면 반드시 `scripts/` 내의 생성기(`build.py`, `pages.py`) 혹은 템플릿(코드 내부)을 수정하고 빌드 스크립트를 재실행해야 합니다.
2.  `news.json` 데이터 및 스키마 임의 변경 금지: 사용자의 명시적인 요청이 없는 한 `news.json`의 원본 데이터나 구조(스키마)를 수정하지 마십시오.
3.  **CSS 변경 제한**: 기존의 CSS 파일은 건드리지 마십시오. 새로운 섹션을 추가할 경우 해당 영역으로 범위를 제한하여 스타일을 적용하십시오.

## GitHub 워크플로 역할

`.github/workflows/` 내의 워크플로는 다음과 같은 역할을 수행합니다.

*   `add-news.yml`: 새로 들어온 소식 데이터를 `news.json`에 추가하고 사이트를 재빌드 및 커밋합니다.
*   `fill-images.yml`: 매일 오전 8시 30분(KST) 및 필요시 실행되어 사진이 누락된 소식에 썸네일을 자동으로 채워 넣습니다.
*   `telegram-notify.yml`: 새 소식이 추가되면 텔레그램 채널로 알림 메시지를 전송합니다.

## PR 규칙

*   PR 제목은 반드시 `[proaudio-wire] 요약` 형식으로 작성합니다.
*   PR을 제출하기 전에는 반드시 빌드 스크립트(`python3 scripts/build.py`)를 실행하여 오류가 없음을 확인하고, 그 실행 결과를 PR 설명 본문에 붙여넣어야 합니다.
*   사이트 표시에 변경이 발생했다면, PR 설명에 변경 전과 변경 후의 차이점을 설명해야 합니다.
