# AI Debate Arena — HF Spaces Docker SDK image.
# Spec 04 §3. HF Spaces builds this on their infra when you push; no local Docker needed.
# Python 3.11 because CrewAI 1.15.1 requires >=3.10,<3.14 (3.11-slim is the safe pick).

FROM python:3.11-slim

WORKDIR /app

# Install deps first so this layer caches when only code changes (Spec 04 §3).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + static frontend. .dockerignore (see repo root) keeps .venv/.env/.git out.
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# HF Spaces Docker SDK expects the app to listen on 7860 by default (Spec 04 §1).
EXPOSE 7860

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
