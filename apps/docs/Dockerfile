FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/docs/package.json apps/docs/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci
COPY apps/docs apps/docs
COPY docs docs
RUN npm run build --workspace @alyvo/docs

FROM nginx:1.27-alpine
COPY apps/docs/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/docs/build /usr/share/nginx/html
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD wget -q -O - http://127.0.0.1:8001/health || exit 1
