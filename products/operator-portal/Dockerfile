# Multi-stage build for the operator portal (SPEC-023 R-1).
#
# Stage 1 compiles the Vite/React SPA from web-ui/app. The build context is
# the repository root (see this product's Makefile) so the root VERSION file
# is visible to vite.config.ts, which injects PLATFORM_VERSION at build time.
#
# Runtime: nginx serves the hashed bundle at / — immutable-cache /assets/,
# no-store index.html with SPA fallback — and proxies /api/ to the gateway
# (SPEC-023 stage 6 removed the legacy vanilla trio).

FROM node:22-alpine AS build

# Mirror the in-repo layout so vite.config.ts resolves ../../../../VERSION.
WORKDIR /workspace/products/operator-portal/web-ui/app

COPY VERSION /workspace/VERSION
COPY products/operator-portal/web-ui/app/package.json \
     products/operator-portal/web-ui/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY products/operator-portal/web-ui/app .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY products/operator-portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/products/operator-portal/web-ui/dist /usr/share/nginx/html

EXPOSE 8080
