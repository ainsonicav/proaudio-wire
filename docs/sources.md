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
| 엔티유시스템즈 (NTU Systems) | http://ntusys.com/ | Tavily extract로 읽기 (https 미지원, 일반 fetch는 시간 초과) | HD 방송장비(비디오 믹서 등) 제조사. 별도 뉴스 게시판 없음 → 메인의 신제품 목록(`/inc/product_view.asp?nnum=` 번호가 커지면 새 제품)으로 신제품 확인. 마지막 확인 nnum=63 (2026-10-13; nnum=62는 HS-100SC HDMI to SDI 스케일 컨버터, nnum=63은 NMS-0112H 3G HD-SDI 분배기 → 새 제품 2건 모두 게시). 참고: 2026-10-11부터 일반 browser.open(http)도 정상 열림. |

## 업계 매체
- Gearspace New Product Alert 게시판 — https://gearspace.com/board/new-product-alert/ (신제품 소식 주요 수집 대상)
- Mixonline, Pro Sound News, AV 업계 전문지 등 공신력 있는 매체
