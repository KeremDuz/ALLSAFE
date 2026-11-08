# Rebuilds the React admin panel and Nginx configuration from this commit.
# The Flutter PhishCatch web client is not built here; it comes from a pinned client
# image on the server (CLIENT), see deploy/server/README.md.
ARG CLIENT
FROM ${CLIENT} AS client

FROM node:22-slim AS admin
WORKDIR /build
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build -- --base=/admin/

FROM nginx:stable-alpine
COPY deploy/home/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=client /usr/share/nginx/html /usr/share/nginx/html
RUN rm -rf /usr/share/nginx/html/admin
COPY --from=admin /build/dist /usr/share/nginx/html/admin
EXPOSE 80
