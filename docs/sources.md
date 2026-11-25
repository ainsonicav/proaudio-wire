# 소식 수집 소스 목록

매일 08:30(한국) 자동 수집 루틴이 이 파일을 읽고 소스를 확인합니다. 소스를 추가·삭제하려면 이 파일만 고치면 됩니다.

## 수집 우선순위
- 최우선: 삼아사운드 공식 취급 브랜드(IK Multimedia, Shure, Genelec, Allen & Heath, PreSonus, HK Audio 등)의 신제품·출시 소식이 있으면 다른 소식보다 먼저 수집한다.

## 날짜 확인 (필수, 2026-10-21 추가)

`incoming/new.json`의 항목마다 **원문 발표일(`sourceDate`)** 을 YYYY-MM-DD로 적는다. `date`(게시일)는 `sourceDate`와 같게 넣는다. `sourceDate`가 없거나 30일 넘게 지난 소식은 `scripts/build.py`가 **거부**한다.

이유: 2026-10-17 dLive V2.0(원문 2024-06-10)과 iLoud Precision MKII(원문 2025-09-09)가 오늘 날짜로 들어가 사이트와 텔레그램에 "최신 뉴스"로 나갔다. 수집 단계가 원문 날짜를 확인하지 않았고, 빌드는 날짜를 검사하지 않았다.

### Gearspace 규칙
- 게시판 목록에는 **2024~2025년 스레드가 섞여 있다**. 목록의 제목만 보고 새 소식으로 판단하지 않는다.
- 스레드를 열어 헤더의 **Start date**를 반드시 확인하고, 그 날짜를 `sourceDate`에 적는다. 30일이 지났으면 수집하지 않는다.
- `New Product Alert`와 `New Product Alert 2 - Older Threads`를 혼동하지 않는다. 후자는 옛 글이 올라오는 곳이다.

## 국내 수입사·유통사
- 삼아프로사운드 (삼아사운드)
- 다산SR — https://blog.naver.com/dasansr

## 제조사
- Yamaha, Shure, L-Acoustics, d&b audiotechnik, Meyer Sound, Sennheiser, Allen & Heath, DiGiCo, QSC, Focusrite, Audio-Technica, Genelec 등

## 업계소식 (국내 업체)
| 업체 | 홈페이지 | 수집 방법 | 메모 |
|---|---|---|---|
| 엔티유시스템즈 (NTU Systems) | http://ntusys.com/ | Tavily extract로 읽기 (https 미지원, 일반 fetch는 시간 초과) | HD 방송장비(비디오 믹서 등) 제조사. 별도 뉴스 게시판 없음 → 메인의 신제품 목록(`/inc/product_view.asp?nnum=` 번호가 커지면 새 제품)으로 신제품 확인. 마지막 확인 nnum=63 (2026-10-13; nnum=62는 HS-100SC HDMI to SDI 스케일 컨버터, nnum=63은 NMS-0112H 3G HD-SDI 분배기 → 새 제품 2건 모두 게시). 2026-11-07 재확인: nnum=64 없음 — curl 시 302로 gabia 오류 페이지로 이동, 브라우저에서도 로드 불가. 참고: 2026-10-11부터 일반 browser.open(http)도 정상 열림. 2026-11-10 재확인: nnum=64 여전히 없음 — browser.open HTTP 500, 라이브 브라우저도 빈 오류 페이지로 로드 실패. 2026-11-11 재확인: nnum=64 여전히 없음 — product_view.asp?nnum=64 browser.open 3회 시도 모두 HTTP 500. 2026-11-13 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패. 2026-11-14 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패(새로고침 동일). 2026-11-15 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패. 2026-11-18 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패(https://errdoc.gabia.io/500.html). 2026-11-19 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패(새로고침 동일). 2026-11-20 재확인: nnum=64 여전히 없음 — browser.open은 네트워크 오류로 실패, 라이브 브라우저는 HTTPS 연결 오류(ERR_SSL_VERSION_OR_CIPHER_MISMATCH) 뒤 가비아 500 오류 페이지로 로드 실패(새로고침 동일, 제품 존재 여부 판단 불가). 2026-11-21 재확인: nnum=64 여전히 없음 — 라이브 브라우저로 홈페이지 로드됨(HTTPS 경고 후 http 접속), 메인 신제품 목록 1페이지 최대 nnum=55(NMS-504S), product_view.asp?nnum=64 직접 접속 시 가비아 500 오류 페이지(https://errdoc.gabia.io/500.html)로 이동. 2026-11-22 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패(새로고침 동일, 제품 존재 여부 판단 불가). 2026-11-23 재확인: nnum=64 여전히 없음 — 라이브 브라우저로 홈페이지 로드됨(HTTPS 경고 후 http 접속), 메인 신제품 목록 최대 nnum=55(NMS-504S). 2026-11-24 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, Tavily CLI는 런타임에 동적 자격증명 도우미가 없어 실행 불가. 2026-11-25 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저로 홈페이지 로드됨(HTTPS 경고 후 http 접속), 메인 신제품 목록 최대 nnum=55(NMS-504S), nnum=64 직접 접속 시 가비아 500 오류 페이지로 이동. 2026-11-26 재확인: nnum=64 여전히 없음 — browser.open 3회 시도 모두 HTTP 500, 라이브 브라우저도 가비아 500 오류 페이지로 로드 실패. 홈페이지는 정상 로드됨, 메인 신제품 목록 최대 nnum=55(NMS-504S). |

## 업계 매체
- Gearspace New Product Alert 게시판 — https://gearspace.com/board/new-product-alert/ (신제품 소식 주요 수집 대상)
- Mixonline, Pro Sound News, AV 업계 전문지 등 공신력 있는 매체

## 자동 수집 (feeds.json, 2026-11-22 추가)

`scripts/collect.py`가 `feeds.json`을 읽어 3시간마다(`collect-feeds.yml`) `incoming/candidates.json`을 만듭니다. 후보는 제목·링크·원문 날짜만 있고 **한국어 요약이 없으므로**, 요약을 붙여 `incoming/new.json`으로 승격해야 사이트에 게시됩니다(요약 없이 게시하면 품질 기준 위반).

| 소스 | 주소 | 종류 | 상태 |
|---|---|---|---|
| Martin Audio | https://martin-audio.com/news/rss.xml | RSS | 200, 1572건(2026-11-18까지) |
| Gearnews | https://gearnews.com/feed/ | RSS | 200, 딜·할인 글은 skipPattern으로 제외 |
| AVNetwork | https://www.avnetwork.com/rss.xml | RSS | 200, 50건 |
| 다산SR | https://rss.blog.naver.com/dasansr.xml | RSS | 200, 50건(국내) |
| 사운드캣 | https://soundcat.co.kr/product_news | HTML(Imweb) | 200, 국내 |
| 인강오디오 | https://ingangaudio.com/ignews | HTML(Imweb) | 200, 국내 |
| 삼아사운드 공지 | https://www.samasound.co.kr/board/free/list.html?board_no=1 | HTML(Cafe24) | 200, 국내 |
| 인터엠 | https://inter-m.com/company/pr_news_list.php | HTML | 200, 국내 |
| 디라직 | https://dlogixs.co.kr/press/ | HTML(KBoard) | 200, 국내(날짜는 상세 페이지에서 확인) |

- **국내 소스는 2026-11-22에 7곳으로 확대**했습니다(다산SR·사운드캣·인강오디오·삼아사운드·인터엠·디라직 + 기존 삼아 취급 브랜드 확인). 국내 제조사·수입사 게시판은 RSS가 없어 HTML 수집으로 붙였습니다.
- 수집 실패/미지원: prosoundweb·mixonline·commercialintegrator는 403(Cloudflare), HK Audio `/feed/`는 빈 값, L-Acoustics `/feed/`는 0건입니다. 이 소스들은 HTML 수집 또는 사람 확인이 필요합니다.
- 소스 추가 절차: ① 주소를 직접 열어 200과 최근 항목 확인 ② `feeds.json`에 항목 추가(`verified`에 확인 날짜·결과 기록) ③ `python3 scripts/collect.py --dry-run`으로 후보가 나오는지 확인.
- 중복 판정: 원문 링크가 같으면 제외, 브랜드+제목이 겹치면 3일 창에서 제외합니다. 제목에 deals/sale/black friday가 들어간 글은 `skipPattern`으로 걸러냅니다.
