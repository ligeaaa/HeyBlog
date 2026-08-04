FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY HeyBlog_Model_API /app/model_api
COPY runtime_resources /app/runtime_resources

RUN pip install --no-cache-dir \
    "/app/model_api/external/HeyBlog_Model[trainer]" \
    "/app/model_api/external/HeyBlog_Model_Agent" \
    "/app/model_api"

WORKDIR /app/model_api
EXPOSE 8040
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8040"]
