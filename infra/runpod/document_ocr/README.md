# Runpod 문서 OCR 워커

이 디렉터리는 자료요약 Agent의 `OCR_PROVIDER=runpod`가 호출하는 Serverless 워커 코드다.

## 입력

- `source_url`: 백엔드가 발급한 짧은 Supabase Storage 서명 URL
- `content_base64`: 작은 파일 로컬 테스트용 Base64 원본
- `file_name`: 원본 파일명
- `media_type`: MIME 타입
- `language`: PaddleOCR 언어. 기본값은 `korean`

## 출력

성공 시 `output.pages`에 1-based 페이지 번호와 Markdown을 반환한다.

```json
{
  "pages": [
    {
      "page_number": 1,
      "markdown": "인식된 내용",
      "source": "paddleocr",
      "ocr_confidence": 0.98
    }
  ]
}
```

## 배포 상태

[진행중]

1. [완료] Dockerfile에서 Runpod GPU용 PaddlePaddle 런타임을 지정한다.
2. [검증] `requirements.txt` 설치를 포함한 호환성 이미지 빌드를 완료한다.
3. [검증] `handler.py`와 모델 파일을 포함한 이미지를 Docker Hub에 push한다.
4. [완료] Serverless endpoint에 `seongbae0201/salesluv-document-ocr:20260827-ocr-compatible` 이미지를 반영한다.
5. [완료] endpoint ID를 백엔드 `OCR_API_URL`에 입력한다.
6. [검증] 새 워커가 `IDLE` 상태로 기동했고 CUDA 런타임 fitness check와 이미지 내부 모델 파일 존재를 확인했다.
7. [검증] Blackwell MIG 워커에서 합성 OCR이 `ocr_empty_result`로 실패한 이력이 있다. 해당 결과는 GPU binary memory allocation warning과 함께 관측됐다.
8. [완료] endpoint를 `AMPERE_24` 풀의 RTX A5000 호환 환경으로 제한하고, 허용 CUDA를 `12.8,13.0`, 최소 CUDA를 `12.8`로 설정했다.
9. [검증] RTX A5000 워커에서 개인정보 없는 합성 명함 OCR을 `COMPLETED`로 재검증했다. 응답에는 페이지 Markdown, `ocr_profile=business_card`, 3개 OCR variant 결과가 포함됐다.
10. [미완료] 실제 업무 문서·실제 명함은 개인정보 외부전송 승인 범위를 확인한 뒤 endpoint에서 재검증한다.

[가정] PaddlePaddle의 CUDA·Python 조합은 선택한 Runpod 이미지에 맞춰 고정해야 한다. 이 저장소에서는 특정 CUDA wheel을 임의로 고정하지 않는다.
