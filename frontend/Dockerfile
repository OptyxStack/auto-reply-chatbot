# Install Node 20 + npm from NodeSource (reliable when official node image has npm issues)
FROM debian:bookworm-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_KEY=dev-key
ARG VITE_ADMIN_API_KEY
ENV VITE_API_KEY=$VITE_API_KEY
ENV VITE_ADMIN_API_KEY=$VITE_ADMIN_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
