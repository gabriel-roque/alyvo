FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=/api/v1
ARG NEXT_PUBLIC_DEMO_TENANT=clinic-alyvo
ARG API_INTERNAL_URL=http://api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_DEMO_TENANT=$NEXT_PUBLIC_DEMO_TENANT
ENV API_INTERNAL_URL=$API_INTERNAL_URL
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm install
COPY apps/web apps/web
COPY packages/contracts packages/contracts
RUN NEXT_OUTPUT=standalone npm run build --workspace @alyvo/web

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV API_INTERNAL_URL=http://api:8000
ENV HOSTNAME=0.0.0.0
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /app/apps/web/public ./apps/web/public
EXPOSE 3000
CMD ["node", "apps/web/server.js"]

