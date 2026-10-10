FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/daemon
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pydantic>=2.9,<3" "argon2-cffi>=23.1,<24" "sqlalchemy>=2.0.36,<3" "psycopg[binary]>=3.2.1,<4"
COPY daemon/synapse_accounts/ /app/daemon/synapse_accounts/
EXPOSE 8788
CMD ["python", "-m", "synapse_accounts", "--host", "0.0.0.0", "--port", "8788"]
