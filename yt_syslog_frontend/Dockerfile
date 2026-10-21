FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx quasar build

FROM nginx:1.27-alpine
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/spa /usr/share/nginx/html
ENV API_UPSTREAM=http://backend:5100
EXPOSE 80
