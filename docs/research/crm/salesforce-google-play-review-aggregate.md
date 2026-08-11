# Salesforce 모바일 Google Play 리뷰 집계

대상 앱: [Salesforce Android 앱](https://play.google.com/store/apps/details?id=com.salesforce.chatter)
스냅샷 기준일: 2026-08-11 UTC

이 문서는 해석이나 프로젝트 타당성 판단을 포함하지 않는다. 수집 방법, 집계 정의, 재현 방법만 기록한다. 개별 리뷰 본문·작성자·리뷰 ID·개발자 답변 원문은 Git에 포함하지 않는다.

## 추적 파일

- `scripts/google_play_reviews.py`: 공개 리뷰 수집, 본문·별점 CSV 생성, 비식별 집계
- `docs/research/crm/salesforce-google-play-review-aggregate-2026-08-11.csv`: 비식별 집계 결과

원본 JSONL과 본문·별점 CSV는 각각 `data/raw/`, `data/processed/`에 생성되며 저장소 정책과 `.gitignore`에 따라 로컬에만 보관한다.

## 재현 명령

```bash
python3 scripts/google_play_reviews.py self-test

python3 scripts/google_play_reviews.py crawl \
  --app-id com.salesforce.chatter

python3 scripts/google_play_reviews.py summarize \
  data/raw/salesforce_chatter_google_play_reviews.jsonl \
  --as-of 2026-08-11 \
  --output data/processed/salesforce-google-play-review-aggregate.csv
```

`crawl`은 표준 라이브러리만 사용한다. 기본 77개 언어 스트림을 최신순으로 조회하며, 중국어 간체(`zh-CN`)와 번체(`zh-TW`)는 별도 스트림으로 처리한다. 각 스트림은 continuation token이 없어질 때까지 조회하고, 반복 token은 오류로 중단한다. 실행 manifest에는 언어별 페이지 수·반환 건수·정상 종료 여부·실패 여부가 남는다.

수집 JSONL은 중복 제거를 위한 `reviewId`를 로컬에 저장하지만 `userName`, `userImage`, `replyContent`는 수집하지 않는다. 스프레드시트 CSV는 `리뷰내용`, `별점` 두 열이며 수식으로 해석될 수 있는 본문은 앞에 작은따옴표를 붙인다.

## 집계 CSV 정의

| 열 | 정의 |
|---|---|
| `section` | 집계 영역: 범위, 전체, 평점, 기간, 언어 스트림, 저평점 주제 등 |
| `segment` | 영역 안의 구간 또는 분류 키 |
| `metric` | 측정 항목 |
| `value` | 집계값 |
| `unit` | `count`, `percent`, `stars`, `timestamp` |
| `denominator` | 비율 또는 분류 건수의 분모 |
| `period_start_utc` | 기간 시작, 포함 |
| `period_end_utc` | 기간 종료, 미포함 |
| `note` | 집계 조건 |
| `source_sha256` | 모든 행에 적용된 로컬 원본 스냅샷 SHA-256 |

- 저평점은 1~2점, 긍정 평점은 4~5점으로 정의한다.
- 기간은 UTC `[시작, 종료)`로 계산한다.
- `language_stream`은 실제 작성 언어 감지가 아니라 Google Play 조회 locale이다.
- `low_review_theme`은 영어 스트림의 1~2점 리뷰에 고정 정규식을 적용한 다중 라벨 건수다. 한 리뷰가 여러 주제에 포함될 수 있다.
- 언어 스트림 표본이 10건 미만이면 개별 집계를 출력하지 않고 `suppressed` 건수로만 기록한다.
- 집계 CSV에는 리뷰 본문, 작성자, 리뷰 ID, 프로필 이미지, 개발자 답변 원문을 출력하지 않는다.

## 범위 제한

- Google Play의 문서화되지 않은 공개 웹 UI 응답을 집계한 스냅샷이다. 앱 화면의 전체 별점 수와 동일한 모집단이 아니다.
- 비공개·삭제·노출 제한·별점만 남긴 평가는 포함되지 않을 수 있다.
- 공개 UI와 RPC 형식은 예고 없이 바뀔 수 있다.
- 앱 소유자가 Play Console에서 받는 전체 이력과 제3자가 공개 UI에서 조회할 수 있는 범위는 다르다. 관련 공식 안내: [Google Play 리뷰 작업 가이드](https://developers.google.com/android-publisher/reply-to-reviews?hl=ko), [지원 스토어 언어](https://support.google.com/googleplay/android-developer/answer/9844778?hl=ko)
