# Build the static bundle, then serve it. The dev server is never shipped:
# `vite` is a development tool and leaves source and HMR exposed.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# nginx-unprivileged runs as uid 101 and listens on 8080 without root.
FROM nginxinc/nginx-unprivileged:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# The UI calls /api/<service>/... and the proxy resolves each one, exactly as
# vite.config.js does in development. Override any of these to match a
# deployment; CASEFORGE_AUTHORIZATION carries the service token, if one is set.
ENV VAULT_URL=http://vault:8000 \
    GENERATOR_URL=http://generator:8001 \
    LIBRARIAN_URL=http://librarian:8002 \
    READER_URL=http://reader:8003 \
    VERIFIER_URL=http://verifier:8004 \
    PUBLISHER_URL=http://publisher:8005 \
    ANALYST_URL=http://analyst:8007 \
    CASEFORGE_AUTHORIZATION=""

EXPOSE 8080
