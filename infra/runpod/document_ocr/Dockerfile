# Runpod Serverless OCR worker image.
# The official PaddlePaddle GPU image supplies the CUDA-compatible runtime;
# the worker-specific Python packages are installed below.
ARG TARGETPLATFORM=linux/amd64
FROM --platform=$TARGETPLATFORM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.0.0-gpu-cuda12.6-cudnn9.5-trt10.5

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    BUSINESS_CARD_MAX_SIDE=2400 \
    PDFIUM_LIB_PATH=/opt/pdfium/libpdfium.so \
    ORT_DYLIB_PATH=/opt/onnxruntime/libonnxruntime.so

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --ignore-installed -r requirements.txt

# pdf-inspector는 PDFium 공유 라이브러리 경로를 명시해야 한다. pypdfium2가
# 현재 플랫폼에 맞는 라이브러리를 설치하므로, 이미지 안의 고정 경로로 복사한다.
RUN python - <<'PY'
from pathlib import Path
import shutil

import pypdfium2_raw

root = Path(pypdfium2_raw.__file__).parent
candidates = sorted(root.glob("libpdfium*"))
if not candidates:
    raise SystemExit(f"pypdfium2_raw PDFium library not found in {root}")
target = Path("/opt/pdfium/libpdfium.so")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(candidates[0], target)
PY

RUN python - <<'PY'
from pathlib import Path
import shutil

import onnxruntime

root = Path(onnxruntime.__file__).parent / "capi"
candidates = sorted(
    path
    for path in root.iterdir()
    if (path.name.startswith("libonnxruntime") or path.name.startswith("onnxruntime"))
    and path.is_file()
)
if not candidates:
    raise SystemExit(f"ONNX Runtime shared library not found in {root}")
target = Path("/opt/onnxruntime/libonnxruntime.so")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(candidates[0], target)
PY

# 한국어 OCR 모델 파일을 이미지에 포함해 Serverless 콜드스타트마다
# Hugging Face에서 모델을 다시 받지 않도록 한다. Mac의 Docker 빌더에는
# NVIDIA libcuda가 없을 수 있으므로 여기서는 모델 파일만 내려받고,
# Paddle 런타임 초기화와 GPU 검증은 Runpod에서 수행한다.
RUN python - <<'PY'
from pathlib import Path

from huggingface_hub import snapshot_download

model_names = (
    "PP-LCNet_x1_0_doc_ori",
    "UVDoc",
    "PP-LCNet_x1_0_textline_ori",
    "PP-OCRv5_server_det",
    "korean_PP-OCRv5_mobile_rec",
)
base = Path("/root/.paddlex/official_models")
for model_name in model_names:
    snapshot_download(
        repo_id=f"PaddlePaddle/{model_name}",
        local_dir=base / model_name,
    )
PY

COPY handler.py ./

CMD ["python", "-u", "/app/handler.py"]
