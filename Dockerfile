FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
# Apply migrations, then serve. (The worker overrides CMD in docker-compose.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
