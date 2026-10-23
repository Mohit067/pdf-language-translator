# ===============================================================
# Optimized Frontend Dockerfile for TransDoc (Next.js Standalone)
# Produces an ultra-lean Alpine image (~140MB) with fast BuildKit caching
# ===============================================================

# ----------------- STAGE 1: Dependencies -----------------------
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit

# ----------------- STAGE 2: Builder ----------------------------
FROM node:20-alpine AS builder
WORKDIR /app

ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . ./

# Persist Next.js' incremental build cache between builds
RUN --mount=type=cache,target=/app/.next/cache \
    npm run build

# ----------------- STAGE 3: Production Runner ------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Run as non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy static assets and standalone server output
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
