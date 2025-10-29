# Placeholder for future web build (React/Next)
FROM node:20-alpine
WORKDIR /app
COPY apps/web/package.json ./
RUN npm install || true
COPY apps/web .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
