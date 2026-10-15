# 저장소 구조 분석 보고서

## 1. 사이트 구성 파일 (HTML, 스크립트, 데이터 파일)

이 사이트는 정적 페이지와 클라이언트 사이드 스크립트, 그리고 백엔드 생성 스크립트로 구성되어 있습니다.

*   **HTML**:
    *   `index.html`: 메인 페이지. 레이아웃, 스타일, 그리고 데이터를 불러와 화면을 그리는 자바스크립트를 포함합니다.
    *   `n/*.html`: 개별 소식 페이지들 (예: `news-100.html`). 구글 검색 노출 및 공유 목적(미리보기)으로 생성됩니다.
*   **스크립트 (Python 및 JS)**:
    *   `scripts/build.py`: 메인 빌드 스크립트로 데이터 유효성 검사, RSS 생성, 통계 계산, 개별 HTML 생성 등을 담당합니다.
    *   `scripts/pages.py`: 개별 소식 HTML(`n/*.html`), 사이트맵(`sitemap.xml`), 그리고 `index.html` 내의 초기 렌더링(Prerender) 부분을 생성하는 로직을 담고 있습니다.
    *   `scripts/fill_images.py`: 뉴스 소식의 이미지를 자동으로 검색하여 채워넣는 스크립트입니다.
    *   `scripts/notify_telegram.py`: 텔레그램 알림용 스크립트입니다.
    *   `index.html` 내장 JS: 브라우저에서 `news.json` 등의 데이터를 동적으로 불러와 화면에 UI(뉴스 리스트, 카드 등)를 그립니다.
*   **데이터 파일 (JSON, XML)**:
    *   `news.json`: 사이트의 핵심 데이터 저장소. 모든 뉴스 소식 항목(아이디, 날짜, 브랜드, 요약 등)이 배열로 들어있습니다.
    *   `stats.json`: 최근 7일/30일 기반의 브랜드 순위와 카테고리 비율 통계 데이터를 담고 있으며, 메인 페이지의 '이번 주 동향' 위젯에서 사용됩니다.
    *   `notices.json`: 상단 공지사항 위젯을 구성하는 데이터입니다.
    *   `rss.xml` 및 `sitemap.xml`: 각각 RSS 피드와 검색 엔진 인덱싱을 위한 파일입니다.

## 2. 페이지 생성 방식 (수동 작성 vs 자동 생성)

페이지의 뼈대는 수동으로 작성되었지만, 주요 콘텐츠와 세부 페이지들은 **데이터(`news.json`)를 바탕으로 스크립트가 자동 생성**하는 하이브리드 구조입니다.

*   **수동 작성 (뼈대)**:
    *   `index.html`: 기본적인 HTML 마크업, CSS 스타일링, 모달 레이아웃, 데이터를 동적으로 렌더링하는 클라이언트 사이드 자바스크립트는 개발자가 수동으로 작성했습니다.
*   **자동 생성 (결과물)**:
    *   `n/*.html` (개별 소식 페이지): `scripts/pages.py` 템플릿에 의해 `news.json` 항목별로 자동 생성됩니다.
    *   `index.html`의 일부분: `<!-- PRERENDER:START -->`와 `<!-- PRERENDER:END -->` 사이의 표(table) 데이터는 `scripts/build.py` 실행 시 최신 데이터로 자동 삽입/갱신됩니다.
    *   `rss.xml`, `sitemap.xml`, `stats.json`: 모두 빌드 스크립트에 의해 자동 생성됩니다.
*   **생성 흐름 (생성기 → 결과물)**:
    *   **생성기**: `scripts/build.py` 및 `scripts/pages.py`
    *   **소스 데이터**: `news.json`
    *   **결과물**: `n/*.html`, `index.html`(일부), `stats.json`, `rss.xml`, `sitemap.xml`

## 3. 자동 배포 및 갱신 설정 (GitHub Actions)

저장소에는 GitHub Actions를 이용한 자동 갱신 및 배포 워크플로우가 설정되어 있습니다.

*   `.github/workflows/fill-images.yml`:
    *   **실행 조건**: `main` 브랜치에 `news.json`이나 스크립트 파일이 Push 될 때, 또는 매일 한국 시간 오전 8:30(cron: `30 23 * * *`)에 자동 실행됩니다.
    *   **작업 내용**:
        1.  `scripts/fill_images.py`를 실행하여 이미지가 없는 뉴스 항목에 사진을 자동 채워 넣습니다.
        2.  `scripts/build.py`를 실행하여 `news.json` 형식을 검사하고 `rss.xml`, `sitemap.xml`, `stats.json`, 개별 `n/*.html`, `index.html`을 갱신합니다.
        3.  변경된 파일들을 봇 권한으로 커밋(`소식 사진 자동 채우기`)하고 저장소에 다시 Push합니다. 이 과정을 통해 사이트 통계와 정적 파일들이 매일 최신 상태로 갱신됩니다.
*   `.github/workflows/telegram-notify.yml`:
    *   새로운 뉴스 소식이 등록되었을 때 텔레그램 채널로 알림을 보내는 워크플로우로 추정됩니다.

## 4. 특정 기능 처리 로직의 위치

1.  **메인 신제품 6선 (`index.html`)**:
    *   **처리 위치**: `index.html` 파일 내부 자바스크립트의 `pickFeatured()` 및 `renderFeatured()` 함수.
    *   **동작 방식**: `newsData` (불러온 `news.json` 데이터) 중에서 `category`가 '프로오디오'인 항목을 필터링합니다. 이때 이미지가 있는 경우(가중치 +2)와 국내 소식인 경우(가중치 +4)에 가중치를 주어 매일 한국 시간 기준 날짜 시드 난수로 6개를 추첨하여 화면 상단의 `#featuredGrid`에 카드로 렌더링합니다.

2.  **브랜드별 집계 (Yamaha와 야마하뮤직코리아가 따로 집계됨) (`scripts/build.py`)**:
    *   **처리 위치**: `scripts/build.py` 파일의 `compute_stats(items)` 함수 내부.
    *   **동작 방식**: `news.json` 내의 `brand` 필드 값을 기준으로 Python의 `Counter`를 이용해 최근 7일 소식의 개수를 셉니다 (`brand_counts = Counter((i.get("brand") or "").strip() ...)`). 별도의 정규화나 매핑 과정 없이 문자열 그대로 집계하기 때문에 `news.json`에 기록된 "Yamaha"와 "야마하뮤직코리아"는 서로 다른 문자열로 인식되어 별도로 집계됩니다. 이 집계 결과는 `stats.json` 파일의 `top_brands_week` 항목에 저장됩니다.

3.  **공유용 `og:image` 메타태그 (`scripts/pages.py`)**:
    *   **처리 위치**: `scripts/pages.py` 파일의 `render_page(it, related)` 함수 내부.
    *   **동작 방식**: 개별 뉴스 소식용 HTML 페이지(`n/*.html`)를 생성할 때, `news.json`의 `imageUrl` 값이 존재하는 경우 `<meta property="og:image" content="{e(img)}">` 태그를 `PAGE` 템플릿의 `{og_image}` 영역에 포맷팅하여 삽입합니다. 이로 인해 각 뉴스 페이지 링크를 외부 메신저로 공유할 때 해당 제품의 사진이 미리보기로 나타납니다.
