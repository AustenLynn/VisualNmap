# Stage 1: build the React frontend (Node never ships in the final image)
FROM node:20-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + nmap
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends nmap \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /src/frontend/dist ./static
ENV VISUALNMAP_HOST=0.0.0.0 \
    VISUALNMAP_PORT=8765 \
    VISUALNMAP_IN_CONTAINER=1 \
    VISUALNMAP_DATA=/data \
    VISUALNMAP_STATIC=/app/static \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "visualnmap"]
