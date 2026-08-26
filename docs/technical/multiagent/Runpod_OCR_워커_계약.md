# Runpod OCR 워커 계약

## 목적

[추론] 스캔 PDF·이미지·명함 OCR은 메인 FastAPI 프로세스와 분리한 Runpod Serverless 워커에서 처리한다. 메인 백엔드는 원본 파일을 직접 GPU 환경에 설치하지 않고, 워커에 문서 위치와 파일 메타데이터만 전달한다.

Runpod Serverless의 동기 호출 주소는 다음 형식이다.

```text
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/runsync?wait=120000
Authorization: Bearer {RUNPOD_API_KEY}
```

[검증] Runpod 공식 문서의 Serverless 요청은 `input` 객체를 포함해야 하며, 동기 요청은 `/runsync`, 비동기 요청은 `/run`을 사용한다. 현재 자료요약 Agent의 1차 어댑터는 문서 처리 호출을 단순하게 유지하기 위해 `/runsync`를 사용한다.

## 요청 입력

워커는 `source_url`과 `content_base64` 중 하나를 받는다. `source_url`이 있으면 이를 우선한다.

```json
{
  "input": {
    "file_name": "contract.pdf",
    "media_type": "application/pdf",
    "language": "korean",
    "source_url": "https://temporary-signed-url"
  }
}
```

서명 URL을 만들 수 없는 로컬 테스트에서는 작은 파일에 한해 다음 형식을 사용한다.

```json
{
  "input": {
    "file_name": "business-card.png",
    "media_type": "image/png",
    "language": "korean",
    "content_base64": "..."
  }
}
```

[추론] 큰 파일은 Base64 payload 대신 Supabase Storage의 짧은 서명 URL을 사용해야 한다. Runpod 공식 문서에 기재된 `/runsync` 최대 payload가 있으므로, 현재 백엔드는 inline 전송을 14 MiB 이하로 제한한다.

## 응답 계약

워커는 `output.pages`를 반환해야 한다. 페이지마다 `markdown` 또는 `lines` 중 하나를 제공한다.

```json
{
  "output": {
    "pages": [
      {
        "page_number": 1,
        "markdown": "## 계약기간\n12개월",
        "source": "paddleocr",
        "ocr_confidence": 0.98
      }
    ]
  }
}
```

또는 line 기반 응답:

```json
{
  "output": {
    "pages": [
      {
        "page_number": 1,
        "lines": [
          {"content": "대표이사 홍길동", "confidence": 0.99}
        ]
      }
    ]
  }
}
```

페이지 번호는 1부터 시작해야 한다. 백엔드는 이 값을 `extracted_payload.pages`, RAG 청크의 `page_start`, `page_end`로 전달한다.

## 환경변수

```env
OCR_PROVIDER=runpod
OCR_API_URL=https://api.runpod.ai/v2/{ENDPOINT_ID}
OCR_API_KEY=
OCR_LOCAL_LANGUAGE=korean
OCR_RUNPOD_WAIT_SECONDS=120
OCR_RUNPOD_INLINE_MAX_BYTES=14680064
OCR_RUNPOD_SIGNED_URL_EXPIRES_SECONDS=300
```

API 키는 저장소·로그·프론트엔드에 기록하지 않는다.

## 다음 구현 범위

[미완료]

1. Runpod 이미지에 PaddleOCR·PDFium·필요한 런타임 설치
2. `handler.py`에서 `source_url`·`content_base64` 입력 처리
3. PDF 페이지 렌더링 및 OCR 결과를 위 응답 계약으로 변환
4. Runpod 콘솔의 실제 endpoint로 스캔 PDF·명함 테스트
5. 처리시간·실패율·콜드스타트·GPU 비용 기록
