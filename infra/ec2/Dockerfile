# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS web-builder
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.12-slim AS python-builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --prefix=/install ".[ollama]"

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/alpha-kapex/SuperShield"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN groupadd --system --gid 10001 supershield \
 && useradd --system --uid 10001 --gid supershield --no-create-home supershield
WORKDIR /app
COPY --from=python-builder /install /usr/local
COPY fixtures ./fixtures
COPY --from=web-builder /web/dist ./web/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=2)" || exit 1
CMD ["sh", "-c", "uvicorn supershield.api:app --host 0.0.0.0 --port ${PORT:-8000}"]