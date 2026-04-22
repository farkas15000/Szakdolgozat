### Stage 1: Frontend build ###
FROM node:lts-alpine AS frontend
WORKDIR /app/src/frontend

COPY src/frontend/package*.json ./
RUN npm install

COPY src/frontend .

RUN npm run build


### Stage 2: Backend runtime ###
FROM python:3.11-slim AS backend

WORKDIR /app
ENV PYTHONPATH="/app"

# Install Postgres client tools (for pg_isready)
RUN apt-get update && apt-get install -y postgresql-client && apt-get clean

RUN apt-get update && apt-get install -y libgomp1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

COPY --from=frontend /app/src/frontend/dist ./dist

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["uvicorn", "src.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
