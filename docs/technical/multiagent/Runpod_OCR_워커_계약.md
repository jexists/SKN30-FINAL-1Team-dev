# Runpod OCR 워커 계약

## 목적

[추론] 스캔 PDF·이미지·명함 OCR은 메인 FastAPI 프로세스와 분리한 Runpod Serverless 워커에서 처리한다. 메인 백엔드는 원본 파일을 직접 GPU 환경에 설치하지 않고, 워커에 문서 위치와 파일 메타데이터만 전달한다.

공개 MinerU 워커를 사용할 때는 백엔드 `.env`에 `OCR_RUNPOD_CONTRACT=mineru`를 설정한다.
이 모드는 `file_url`/`file_b64` 입력과 `output.results[].markdown` 응답을 프로젝트의
페이지별 Markdown 구조로 정규화한다. 자체 `infra/runpod/document_ocr` 워커를 배포할 때는
기본값인 `salesluv`를 사용한다.

Runpod Serverless의 동기 호출 주소는 다음 형식이다.

```text
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/runsync?wait=120000
Authorization: Bearer {RUNPOD_API_KEY}
```

[검증] Runpod 공식 문서의 Serverless 요청은 `input` 객체를 포함해야 하며, 동기 요청은 `/runsync`, 비동기 요청은 `/run`을 사용한다. 현재 자료요약 Agent의 1차 어댑터는 문서 처리 호출을 단순하게 유지하기 위해 `/runsync`를 사용한다.

## 요청 입력

자체 워커는 `source_url`과 `content_base64` 중 하나를 받는다. `source_url`이 있으면 이를 우선한다.
명함 스캔은 `profile=business_card`를 함께 보내며, 워커는 방향 분류·원근 보정·대비/이진화 variant OCR을 적용한다.

```json
{
  "input": {
    "file_name": "contract.pdf",
    "media_type": "application/pdf",
    "language": "korean",
    "profile": "document",
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
    "profile": "business_card",
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
BUSINESS_CARD_MAX_SIDE=2400
```

API 키는 저장소·로그·프론트엔드에 기록하지 않는다.

## 다음 구현 범위

[진행중]

1. [완료] Runpod 이미지에 PaddleOCR·PDFium·필요한 런타임 설치 정의
2. [완료] `handler.py`에서 `source_url`·`content_base64` 입력 처리
3. [완료] 명함 프로필의 방향·원근 보정 및 다중 variant OCR 정의
4. [완료] PDF 페이지 렌더링 및 OCR 결과를 위 응답 계약으로 변환
5. [완료] 호환성 이미지 `seongbae0201/salesluv-document-ocr:20260827-ocr-compatible`를 빌드·배포하고 endpoint 이미지에 반영
6. [검증] 새 워커 기동, CUDA 런타임 확인, 이미지 내부 PaddleOCR 모델 파일 포함을 확인
7. [검증] Blackwell MIG 워커에서 합성 OCR이 `ocr_empty_result`로 실패한 이력이 있다. GPU binary memory allocation warning도 함께 관측됐다.
8. [완료] endpoint를 `AMPERE_24` 풀의 RTX A5000 호환 환경으로 제한하고 허용 CUDA를 `12.8,13.0`, 최소 CUDA를 `12.8`로 설정
9. [검증] RTX A5000 워커에서 개인정보 없는 합성 명함 OCR을 `COMPLETED`로 재검증. 응답에 페이지 Markdown과 `ocr_profile=business_card`, 3개 variant 결과가 포함됨
10. [미완료] 실제 업무 문서·실제 명함은 개인정보 외부전송 승인 범위를 확인한 뒤 endpoint에서 재검증
11. [미완료] 처리시간·실패율·콜드스타트·GPU 비용 기록
