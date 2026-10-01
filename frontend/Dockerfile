# syntax=docker/dockerfile:1

FROM oven/bun:1 AS build

WORKDIR /app

# Camada de dependências isolada do código para aproveitar o cache do Docker.
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
# VITE_API_URL fica sem definir de propósito: o bundle usa "/api", que o nginx
# reescreve para a API.
RUN bun run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
