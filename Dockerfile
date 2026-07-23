FROM node:24-alpine

WORKDIR /app

COPY telegram-mini-app/package*.json ./
RUN npm ci

COPY telegram-mini-app/ ./

ARG VITE_API_BASE_URL=https://bloomclub.ru/api/v1
ARG VITE_TG_LOCAL_CATALOG_ENABLED=true
ARG VITE_TG_API_BASE_URL=

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TG_LOCAL_CATALOG_ENABLED=$VITE_TG_LOCAL_CATALOG_ENABLED
ENV VITE_TG_API_BASE_URL=$VITE_TG_API_BASE_URL

RUN npm run build

ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0

# Timeweb may override PORT or provide another runtime port env; server/production-server.js detects supported port env candidates.
EXPOSE 3000

CMD ["node", "server/production-server.js"]
