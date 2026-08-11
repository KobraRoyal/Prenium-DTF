FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

RUN apk add --no-cache curl

COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
# Use a path that Synology empty-volume mounts cannot shadow (/var/www/static was overridden).
COPY backend/static_src/ /usr/share/nginx/prenium-static/
