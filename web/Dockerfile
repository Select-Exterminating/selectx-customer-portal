# Next.js BFF. API_URL and APP_ORIGINS are read at runtime; the build doesn't call the API.
FROM node:22-slim

RUN npm install --global pnpm@10.27.0

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /srv
RUN chown node:node /srv
USER node

COPY --chown=node:node package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY --chown=node:node . .
RUN pnpm build

ENV NODE_ENV=production
EXPOSE 3001
CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3001"]
