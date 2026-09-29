# ==============================================================================
# Multi-Stage Dockerfile for StrategyOne Multi-Agent Quantitative Trading Platform
# ==============================================================================

# Stage 1: Build the Modern React / Vite Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python Runtime Environment
FROM python:3.11-slim AS runner
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Install system dependencies (build-essential, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source code
COPY . .

# Copy pre-built frontend distribution from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose API and UI port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Start FastAPI server serving both API and Frontend SPA
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
