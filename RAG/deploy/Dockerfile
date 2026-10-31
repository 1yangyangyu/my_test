FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
ENV TOWER_DATA_DIR=/data TOWER_MODE=local
EXPOSE 8000
CMD ["uvicorn", "tower_kb.main:app", "--host", "0.0.0.0", "--port", "8000"]
