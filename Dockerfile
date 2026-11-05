# CareLoop backend with the patient app and dashboard on one address (Railway, or any Docker host).
# The frontend is built with the real backend as its default (VITE_USE_MOCKS=0); FastAPI serves frontend/dist.
# Keys come from the host's settings, never from this image. The voice worker deploys separately (voice/Dockerfile).

FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_USE_MOCKS=0
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN adduser --disabled-password --gecos "" --home /app --uid 10001 appuser
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY data/ data/
COPY voice/prompts/ voice/prompts/
COPY --from=frontend /src/frontend/dist frontend/dist
RUN chown -R appuser:appuser /app
USER appuser

WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
