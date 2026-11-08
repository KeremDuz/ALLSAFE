# Applies this commit's public Nginx configuration. The Flutter public web client comes
# from a pinned client image on the server (CLIENT), see deploy/server/README.md.
ARG CLIENT
FROM ${CLIENT} AS client

FROM nginx:stable-alpine
COPY deploy/public/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=client /usr/share/nginx/html /usr/share/nginx/html
