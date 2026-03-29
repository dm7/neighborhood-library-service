FROM node:22-alpine

WORKDIR /app

COPY frontend/package.json ./
RUN npm install

COPY frontend ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
