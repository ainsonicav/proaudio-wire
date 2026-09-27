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
- `status`를 `hidden`으로 바꾸면 사이트에서 숨겨집니다.
