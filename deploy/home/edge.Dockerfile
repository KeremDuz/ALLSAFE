FROM node:22-slim AS admin
WORKDIR /build
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build -- --base=/admin/

FROM nginx:stable-alpine
COPY deploy/home/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=admin /build/dist /usr/share/nginx/html/admin
# Built by Flutter locally/CI, with same-origin ALLSAFE and managed mode enabled.
COPY build/home-client/web /usr/share/nginx/html
EXPOSE 80
