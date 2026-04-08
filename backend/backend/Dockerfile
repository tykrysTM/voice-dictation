# Voice Dictation Backend
# Multi-stage build: build → runtime

FROM python:3.12-slim as build
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download whisper model (large-v3 ~3GB)
RUN python -c "from transformers import AutoModelForSpeechSeq2Seq, AutoFeatureExtractor; import torch; \
    model = AutoModelForSpeechSeq2Seq.from_pretrained('openai/whisper-large-v3', torch_dtype=torch.float16); \
    feature_extractor = AutoFeatureExtractor.from_pretrained('openai/whisper-large-v3'); \
    model.save_pretrained('/models/whisper-large-v3'); \
    feature_extractor.save_pretrained('/models/whisper-feature')"

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /models /models
COPY main.py .
COPY requirements.txt .

# Expose port
EXPOSE 8000

# Run
CMD ["python", "main.py"]
