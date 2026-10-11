FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de

RUN apk add --no-cache curl

COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
# Use a path that Synology empty-volume mounts cannot shadow (/var/www/static was overridden).
COPY backend/static_src/ /usr/share/nginx/prenium-static/
