FROM python:3.11-slim

# Build context must be the repo root (docker build -f backend/Dockerfile .)
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# Run uvicorn as a package from the repo root so relative imports resolve
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
