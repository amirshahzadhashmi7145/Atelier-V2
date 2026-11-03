# syntax=docker/dockerfile:1

# Agent Studio web (Next.js). NEXT_PUBLIC_* values are inlined at build time, so the
# public API URL must be passed as a build arg.
FROM node:22-bookworm-slim AS base
RUN corepack enable
WORKDIR /app/web

FROM base AS deps
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/web/node_modules ./node_modules
COPY web/ ./
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_USE_MOCKS=false
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_USE_MOCKS=$NEXT_PUBLIC_USE_MOCKS \
    NODE_ENV=production
RUN pnpm build

FROM base AS run
ENV NODE_ENV=production
COPY --from=build /app/web/.next ./.next
COPY --from=build /app/web/public ./public
COPY --from=build /app/web/node_modules ./node_modules
COPY --from=build /app/web/package.json ./package.json
COPY --from=build /app/web/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
