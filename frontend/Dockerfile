# Development image: Vite dev server with hot reload. A production build
# (nginx serving `vite build` output) is a Sprint 8 concern (T-613).
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
