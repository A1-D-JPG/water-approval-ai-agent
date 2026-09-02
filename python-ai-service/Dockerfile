FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

# 瀹夎涓枃 OCR 杩愯鐜鍙婄瀛﹁绠楀簱闇€瑕佺殑绯荤粺渚濊禆銆?
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 鍒╃敤 Docker 缂撳瓨锛氫笟鍔′唬鐮佸彉鍖栨椂鏃犻渶閲嶆柊瀹夎鍏ㄩ儴渚濊禆銆?
COPY requirements.txt .

# 褰撳墠閮ㄧ讲鍙娇鐢?CPU 鎺ㄧ悊銆傚厛瀹夎 CPU-only PyTorch锛?
# 閬垮厤 sentence-transformers 闂存帴瀹夎 CUDA銆乧uDNN 鍜?Triton銆?
RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.13.0" \
    && python -m pip install -r requirements.txt \
    && python -m pip check

COPY app ./app
COPY main.py ai_core.py mcp_server.py ./
COPY knowledge_docs ./knowledge_docs

RUN mkdir -p /app/chroma_db /app/data/evals

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
