FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
# Use a path that Synology empty-volume mounts cannot shadow (/var/www/static was overridden).
COPY backend/static_src/ /usr/share/nginx/prenium-static/
