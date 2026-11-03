# Tomi voice worker for LiveKit Cloud or any Docker host. Adapted from github.com/Tech-sis123/agricall.
# Build from this folder:  docker build -t careloop-tomi voice/
# Keys come from the host's settings (LiveKit Cloud: `lk agent create` / secrets), never from this image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN adduser --disabled-password --gecos "" --home /app --uid 10001 appuser
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

CMD ["python", "tomi_agent.py", "start"]
