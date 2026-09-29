# 빌드 컨텍스트는 저장소 루트 — schema/ 를 함께 넣어야 해서 (security-dashboard 와 같은 방식)
#   docker build -f api-server/Dockerfile -t mechdog-api .
FROM python:3.11-slim
WORKDIR /srv
COPY api-server/requirements.txt api-server/requirements.txt
RUN pip install --no-cache-dir -r api-server/requirements.txt
COPY schema/ schema/
COPY api-server/app/ api-server/app/
WORKDIR /srv/api-server
ENV SCHEMA_PATH=/srv/schema/mechdog_messages.schema.json API_LOG_DIR=/data/logs
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
