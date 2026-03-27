FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml readme.md ./
COPY app ./app
COPY shared ./shared
COPY backend ./backend
COPY crawler ./crawler
COPY persistence_api ./persistence_api
COPY search ./search
COPY frontend ./frontend
COPY services ./services
COPY --from=frontend-builder /frontend/dist ./frontend/dist
COPY seed.csv ./seed.csv

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
