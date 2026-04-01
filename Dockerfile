FROM python:3.11-slim

WORKDIR /app

# Install Postgres client tools (for pg_isready)
RUN apt-get update && apt-get install -y postgresql-client && apt-get clean

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]
