FROM node:18-bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends chromium ffmpeg && \
    rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV REMOTION_BROWSER_EXECUTABLE=/usr/bin/chromium
ENV REMOTION_BUNDLE_PATH=/app/remotion
ENV OUTPUT_DIR=/output

WORKDIR /app

COPY service/package.json service/package-lock.json ./
RUN npm ci

COPY service/tsconfig.json ./
COPY service/src/ ./src/

COPY package.json package-lock.json /app/remotion/
COPY tsconfig.json /app/remotion/
COPY src/ /app/remotion/src/
COPY public/ /app/remotion/public/

RUN cd /app/remotion && npm ci

RUN npm run build

EXPOSE 3100
CMD ["node", "dist/server.js"]
