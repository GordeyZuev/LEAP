# Multi-stage build for Next.js with `output: 'standalone'`.
# Final image only contains the standalone server + minimal runtime — no source, no devDeps.

# -----------------------------------------------------------------------------
# Stage 1: deps — install pnpm dependencies from a frozen lockfile
# -----------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app

RUN npm install -g pnpm@11.5.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile


# -----------------------------------------------------------------------------
# Stage 2: builder — compile the Next.js app
# -----------------------------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app

RUN npm install -g pnpm@11.5.0

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Empty — apiClient appends "/api/v1"; "/api" here → "/api/api/v1" → 404.
ENV NEXT_PUBLIC_API_URL=
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm run build


# -----------------------------------------------------------------------------
# Stage 3: runner — minimal runtime image
# -----------------------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as non-root for defense in depth
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# Standalone output: server.js + bundled node_modules
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
