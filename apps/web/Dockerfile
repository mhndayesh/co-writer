FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* vars are inlined into the client bundle at BUILD time, so they
# must be present here — passing them only at runtime has no effect. Without
# this, the production frontend shipped hardcoded to http://localhost:8080.
# Provide via `--build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.com`.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_CDN_URL
# Clerk's publishable key is a NEXT_PUBLIC_* var: it must be present at BUILD time
# to be inlined into the client bundle, or @clerk/nextjs has no key in the browser.
# (The matching CLERK_SECRET_KEY is a runtime-only var supplied via .env.production.)
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_CDN_URL=$NEXT_PUBLIC_CDN_URL
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
