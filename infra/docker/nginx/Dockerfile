FROM nginx:1.31-alpine@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752

RUN apk add --no-cache curl

COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
# Use a path that Synology empty-volume mounts cannot shadow (/var/www/static was overridden).
COPY backend/static_src/ /usr/share/nginx/prenium-static/
