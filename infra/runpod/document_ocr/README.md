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

## 배포 전 확인

[미완료]

1. Runpod GPU 템플릿에 PaddlePaddle 런타임을 설치한다.
2. `requirements.txt`를 설치한다.
3. `handler.py`를 Serverless endpoint의 handler로 등록한다.
4. Runpod 콘솔에서 이미지와 PDF를 각각 테스트한다.
5. 실제 endpoint ID를 백엔드 `OCR_API_URL`에 입력한다.

[가정] PaddlePaddle의 CUDA·Python 조합은 선택한 Runpod 이미지에 맞춰 고정해야 한다. 이 저장소에서는 특정 CUDA wheel을 임의로 고정하지 않는다.
