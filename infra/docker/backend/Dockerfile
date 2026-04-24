# Étape CSS : Tailwind compile input.css (+ legacy) vers app.css servi par Django / collectstatic
FROM node:20-alpine AS css
WORKDIR /build
COPY backend/package.json backend/package-lock.json ./
RUN npm ci
COPY backend/tailwind.config.js backend/postcss.config.js ./
COPY backend/static_src ./static_src
RUN npm run build:css

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements /tmp/requirements
RUN pip install --upgrade pip && pip install -r /tmp/requirements/prod.txt

COPY . /app
COPY --from=css /build/static_src/css/app.css /app/backend/static_src/css/app.css

RUN chmod +x infra/scripts/*.sh && \
    mkdir -p /app/backend/var/media /app/backend/staticfiles
