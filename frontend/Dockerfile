FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . .
ARG VITE_API_BASE
ARG VITE_APP_ENV=staging
ARG VITE_ANALYTICS_ENABLED=false
ARG VITE_AMPLITUDE_API_KEY
# Бот для ссылок «поделиться» и карточки сторис (по умолчанию cosmi_bbot).
ARG VITE_BOT_USERNAME
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
