# Runpod 문서 OCR 워커

이 디렉터리는 자료요약 Agent의 `OCR_PROVIDER=runpod`가 호출하는 Serverless 워커 코드다.

## 입력

- `source_url`: 백엔드가 발급한 짧은 Supabase Storage 서명 URL
- `content_base64`: 작은 파일 로컬 테스트용 Base64 원본
- `file_name`: 원본 파일명
- `media_type`: MIME 타입
- `language`: PaddleOCR 언어. 기본값은 `korean`

`runsync`가 바로 완료되지 않고 job ID와 `IN_QUEUE`·`IN_PROGRESS`를 반환하는 경우, 백엔드가
상태 조회 API를 폴링해 최종 `output.pages`를 받은 뒤 다음 처리 단계로 넘긴다.

### [알려진 제약] PDF 경로는 `language`를 쓰지 않는다

`language`는 이미지 경로(`_image_page` -> `_paddle_engine(language)`)에만 전달된다. PDF는
`_pdf_pages`가 `pdf_inspector.process_pdf_with_ocr_bytes(content)`를 언어 인자 없이 부르므로
스캔된 한글 PDF에서 한글이 깨지고 ASCII 숫자만 살아남는다. 텍스트 PDF는 임베디드 텍스트를
뽑기 때문에 영향이 없다.

백엔드는 이 워커를 재배포하지 않고 우회한다. 사업자등록증 인식은 회사명과 주소가 둘 다 비면
`ocr.render_pdf_page_png`로 첫 장을 PNG로 구워 이미지 경로로 다시 보낸다
(`app/services/business_license_scans.py`). 다음에 워커를 재배포할 때 `_pdf_pages`가 `language`를
받아 쓰도록 고치면 이 우회를 걷어낼 수 있다.

PDF는 워커 내부에서 페이지를 4개 단위로 나눠 처리한다. 긴 PDF 전체를 한 번에 OCR하지 않아
GPU 메모리 부담을 낮추고, 각 페이지의 번호와 Markdown을 유지한다.

PDFium은 `pypdfium2`가 설치한 현재 플랫폼용 공유 라이브러리를 `/opt/pdfium/libpdfium.so`로
고정하고 `PDFIUM_LIB_PATH`로 지정한다. 실행 시에도 패키지 경로를 자동 탐색해 Mac·Windows·Linux
환경에서 경로 차이로 PDF 처리가 실패하지 않도록 한다.
ONNX Runtime도 `onnxruntime==1.23.2`를 이미지에 포함하고 `/opt/onnxruntime/libonnxruntime.so`를
`ORT_DYLIB_PATH`로 지정해 `pdf-inspector`의 `OrtGetApiBase` 로딩 오류를 방지한다.

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
4. [검증] Serverless endpoint에 `seongbae0201/salesluv-document-ocr:20260831-runpod-worker-ocr-fix` 이미지를 반영한다.
5. [완료] endpoint ID를 백엔드 `OCR_API_URL`에 입력한다.
6. [검증] 새 워커가 `IDLE` 상태로 기동했고 CUDA 런타임 fitness check와 이미지 내부 모델 파일 존재를 확인했다.
7. [검증] Blackwell MIG 워커에서 합성 OCR이 `ocr_empty_result`로 실패한 이력이 있다. 해당 결과는 GPU binary memory allocation warning과 함께 관측됐다.
8. [완료] endpoint를 `AMPERE_24` 풀의 RTX A5000 호환 환경으로 제한하고, 허용 CUDA를 `12.8,13.0`, 최소 CUDA를 `12.8`로 설정했다.
9. [검증] RTX A5000 워커에서 개인정보 없는 합성 명함 OCR을 `COMPLETED`로 재검증했다. 응답에는 페이지 Markdown, `ocr_profile=business_card`, 3개 OCR variant 결과가 포함됐다.
10. [검증] 백엔드 `OCR_PROVIDER=runpod` 어댑터에서 개인정보 없는 합성 명함을 호출해 `provider=runpod`, 페이지 Markdown, 1-based 페이지 번호, job id 변환을 확인했다.
11. [검증] 백엔드 Runpod 어댑터에서 개인정보 없는 합성 PDF를 호출해 페이지 Markdown과 연속 페이지 번호 변환을 확인했다.
12. [검증] Runpod 비동기 `/run` 제출 후 job 상태 조회로 합성 PDF 1건을 `COMPLETED`까지 확인했다. 2026-08-27 관측 시간은 15.32초이며 운영 평균으로 사용하지 않는다.
13. [검증] 승인된 실제 명함 이미지 1건은 새 endpoint에서 OCR 처리해 페이지 Markdown·텍스트 생성을 확인했다. 원문은 출력하거나 저장하지 않았다.
14. [검증] PDFium 공유 라이브러리 경로 보강 이미지 `seongbae0201/salesluv-document-ocr:20260827-pdfium`을 배포한 뒤 실제 취업규칙 PDF 35페이지 OCR을 재검증했다. 페이지 번호 연속성·Markdown·텍스트 생성을 확인했다.
15. [검증] 위 Runpod OCR 결과를 OpenAI Responses API의 `gpt-5.6-luna` 구조화 요약으로 전달해 핵심 요약·주요 내용·리스크·추출 필드 결과를 생성했다. 원문과 요약 본문은 출력하지 않았다.
16. [검증] `onnxruntime==1.23.2`와 공유 라이브러리 경로 보강 이미지를 배포한 뒤 합성 PDF OCR을 `COMPLETED`로 재검증했다. 백엔드의 비동기 상태 폴링도 열린 HTTP 세션 안에서 완료됨을 확인했다.
17. [검증] Linux GPU 워커의 PaddleOCR 명함 엔진에 `enable_mkldnn=False`를 적용한 이미지를 배포했다. 새 워커가 `IDLE`로 기동했고 개인정보 없는 합성 명함 결과가 1페이지·오류 없음·OCR confidence 0.983으로 반환됐다.

[가정] PaddlePaddle의 CUDA·Python 조합은 선택한 Runpod 이미지에 맞춰 고정해야 한다. 이 저장소에서는 특정 CUDA wheel을 임의로 고정하지 않는다.

## 안전한 연결 점검

개인정보 없는 합성 입력만 사용해 백엔드 어댑터와 Runpod endpoint를 함께 점검한다.

```bash
cd backend
OCR_PROVIDER=runpod \\
OCR_API_URL=https://api.runpod.ai/v2/{ENDPOINT_ID} \\
.venv/bin/python scripts/runpod_ocr_smoke.py --case all
```

출력에는 처리 상태·페이지 수·Markdown 생성 여부·관측 처리시간만 포함한다. 실제 문서나
명함을 테스트하려면 파일별 외부 전송 승인을 먼저 확인한다.
