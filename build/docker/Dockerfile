# syntax=docker/dockerfile:1

# Build the React single-page application.
FROM node:20-alpine AS frontend-build
WORKDIR /src/frontend
ARG VITE_DEV_WEBHOOK_TOKEN
ENV VITE_DEV_WEBHOOK_TOKEN=${VITE_DEV_WEBHOOK_TOKEN}
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Install Python dependencies in a small, reproducible runtime image.
FROM python:3.11-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY build/docker/run-migrations.sh /usr/local/bin/run-migrations
COPY build/docker/run-migrations.py /usr/local/bin/run-migrations.py
RUN chmod +x /usr/local/bin/run-migrations
EXPOSE 8137
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8137"]

# Serve the compiled UI and proxy API requests to the API service.
FROM nginx:1.27-alpine AS frontend
COPY build/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /src/frontend/dist /usr/share/nginx/html
EXPOSE 80
