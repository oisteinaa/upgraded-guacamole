FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Oslo \
    DAS_BIND_HOST=0.0.0.0 DAS_PORT=8051
WORKDIR /app
COPY requirements-map.txt requirements-reports.txt ./
RUN pip install --no-cache-dir -r requirements-reports.txt
COPY src/ ./src/
COPY --from=frontend /build/dist ./web/dist/
EXPOSE 8051
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8051/api/health', timeout=3)"
CMD ["python", "-m", "src.Mapui.launcher", "--no-demo"]
