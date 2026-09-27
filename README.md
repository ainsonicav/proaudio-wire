# proaudio-wire

PRO AUDIO WIRE — https://news.ainsonic.com (GitHub Pages)

## 구조

| 파일 | 역할 |
|---|---|
| `index.html` | 화면. 열릴 때 `news.json`을 읽어서 그림 (데이터를 HTML에 넣지 않음) |
| `news.json` | 소식 데이터 (배열, 위에 있을수록 먼저 표시 / 앞 6건이 "주요 6선") |
| `rss.xml` | `scripts/build.py`가 `news.json`으로 자동 생성 |
| `scripts/build.py` | `news.json` 형식 검사 + `rss.xml` 생성 |

## 자동 업데이트가 할 일

1. `news.json`만 갱신해서 커밋 (index.html은 건드리지 않음)
2. `python3 scripts/build.py` 실행 → 검사 통과 시 `rss.xml` 갱신
3. 검사 실패(칸 밀림, 빈 값 등)면 커밋하지 않음

## news.json 항목 형식

```json
{
  "id": "news-100",
  "date": "2026-09-27",
  "company": "수입사/발표 주체 (예: 삼아프로사운드 (삼아사운드))",
  "brand": "브랜드 (예: Shure)",
  "productName": "제품명",
  "type": "신제품 | 업데이트 | 행사",
  "summary": "한두 문장 요약",
  "link": "https://원문",
  "evidence": "원문 인용 한 줄",
  "status": "published",
  "isDomestic": true,
  "imageUrl": "https://... (선택)"
}
```

- `date`는 **게시일**입니다. 행사 개최일은 summary에 적어 주세요.
- `summary`는 독자(교회·공연장 음향 담당, AV 설치업체, 방송·스튜디오 엔지니어) 입장의 3~4문장, 공백 포함 180~260자(최대 280자):
  ① 누가 무엇을 발표했는지(제품 종류를 쉬운 한국어로) ② 핵심 특징·사양 2~3개(원문 수치 그대로)
  ③ 어디에 쓰는지·무엇이 달라졌는지(원문 근거가 있을 때만) ④ 가격·출시 시기·국내 수입사·행사 일시/장소/신청 방법(있을 때).
  원문에 없는 내용·과장 표현(혁신적인, 획기적인 등) 금지, "~했습니다/~입니다" 체.
- `status`를 `hidden`으로 바꾸면 사이트에서 숨겨집니다.

## 사진 자동 채우기 (썸네일 항상 표시)

`news.json`이 바뀔 때와 매일 오전 8:30에 GitHub Actions(`fill-images.yml`)가 사진이 없는 소식을 채웁니다.

1. 원문의 대표 이미지(og:image)
2. 원문 사이트가 자동 접속을 막으면 페이지 읽기 서비스(r.jina.ai)로 우회
3. 대표 이미지가 없으면 본문 속 큰 사진
4. 그래도 없으면 "브랜드 + 제품명" 이미지 검색 — 브랜드명이 들어간 결과만 사용
   - Google 이미지 검색: SerpApi 키를 저장소 Secret `SERPAPI_KEY`로 등록하면 사용 (무료 월 250회, 한 번 실행에 최대 60회)
   - (Google 자체 검색 API는 신규 가입이 막혀 있고 2027-01-01 종료 예정이라 쓰지 않음)
   - 키가 없거나 실패하면 DuckDuckGo → Bing (GitHub 서버에서는 대부분 막힘)
5. 모두 실패하면 사이트는 브랜드명 디자인 카드를 보여주고, 3일 뒤 다시 시도(`imageTried`)

모든 이미지는 저장 전에 실제로 열리는지 확인합니다. 검색으로 찾은 사진은 `imageSource: "search"`로 표시되고
사이트에 작게 "관련 이미지"라고 나옵니다. 사진을 직접 넣으려면 `imageUrl`에 주소를 적으면 됩니다.
