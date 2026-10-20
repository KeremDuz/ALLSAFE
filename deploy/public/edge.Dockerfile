FROM nginx:stable-alpine
COPY deploy/public/nginx.conf /etc/nginx/conf.d/default.conf
COPY build/public-client/web /usr/share/nginx/html
