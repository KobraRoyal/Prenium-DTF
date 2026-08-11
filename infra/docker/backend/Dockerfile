# Étape CSS : Tailwind compile input.css (+ legacy) vers app.css servi par Django / collectstatic
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS css
WORKDIR /build
COPY backend/package.json backend/package-lock.json ./
RUN npm ci
COPY backend/tailwind.config.js backend/postcss.config.js ./
COPY backend/scripts ./scripts
COPY backend/static_src ./static_src
RUN npm run build:assets

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS runtime

ARG APP_REVISION=unknown
ARG APP_VERSION=dev

LABEL org.opencontainers.image.source="https://github.com/KobraRoyal/Prenium-DTF" \
      org.opencontainers.image.revision="${APP_REVISION}" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --home-dir /app --create-home app

RUN apt-get update && apt-get install -y --no-install-recommends ghostscript gosu && \
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
