FROM python:3.14.6-slim

ARG VCS_REF=unknown
ARG VERSION=0.1.0

LABEL org.opencontainers.image.title="ecloe-engine" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WEB_CONCURRENCY=1

WORKDIR /app

RUN addgroup --system ecloe && adduser --system --ingroup ecloe ecloe

COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
COPY scripts ./scripts
COPY reports ./reports

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -e ".[azure,observability]"

USER ecloe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/livez' % os.getenv('PORT','8000'), timeout=3).read()"

CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
