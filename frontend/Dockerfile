FROM node:20 AS builder
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
