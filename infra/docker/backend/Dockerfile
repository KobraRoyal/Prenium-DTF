# Étape CSS : Tailwind compile input.css (+ legacy) vers app.css servi par Django / collectstatic
FROM node:20-alpine AS css
WORKDIR /build
COPY backend/package.json backend/package-lock.json ./
RUN npm ci
COPY backend/tailwind.config.js backend/postcss.config.js ./
COPY backend/scripts ./scripts
COPY backend/static_src ./static_src
RUN npm run build:assets

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --home-dir /app --create-home app

RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements /tmp/requirements
RUN pip install --upgrade pip && pip install -r /tmp/requirements/prod.txt

COPY . /app
COPY --from=css /build/static_src/css/app.css /app/backend/static_src/css/app.css
COPY --from=css /build/static_src/vendor /app/backend/static_src/vendor

RUN chmod +x infra/scripts/*.sh && \
    mkdir -p /app/backend/var/media /app/backend/staticfiles /var/app/static /var/app/media && \
    chown -R app:app /app /var/app

FROM runtime AS dev

RUN pip install -r /tmp/requirements/dev.txt

FROM runtime AS prod
