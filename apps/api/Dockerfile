FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
COPY packages ./packages

ARG INSTALL_WHISPERX=false
RUN python -m pip install --no-cache-dir --upgrade pip \
    && if [ "$INSTALL_WHISPERX" = "true" ]; then \
        pip install --no-cache-dir -e ".[video,whisperx]"; \
    else \
        pip install --no-cache-dir -e ".[video]"; \
    fi

EXPOSE 8000
CMD ["uvicorn", "cliplab_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
