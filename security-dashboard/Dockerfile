# security-dashboard(MechDog D) - 팀 규칙: 베이스 이미지 python:3.11-slim, 웹 포트 3000.
#
# 주의: 이 Dockerfile은 "저장소 루트"를 빌드 컨텍스트로 기대한다 (security-dashboard/
# 폴더 하나만이 아니라). 이유: mqtt_client.py가 팀의 schema/mechdog_messages.schema.json,
# schema/topics.json을 유일한 스펙으로 읽는데, 그 파일은 security-dashboard/ 바깥
# (저장소 루트의 schema/)에 있기 때문이다. 그래서 이미지 안에서도 로컬 개발 폴더와
# 똑같은 상대 위치(<root>/schema/, <root>/security-dashboard/app/...)를 그대로
# 재현했다 - 코드 수정 없이 로컬/컨테이너 양쪽에서 동일한 경로 계산이 통하게 하기 위해서다.
#
# 빌드 (저장소 루트에서 실행):
#   docker build -f security-dashboard/Dockerfile -t security-dashboard .
#
# 팀 docker-compose.yml에 그대로 끼워 넣으려면 security-dashboard 서비스의
# build.context를 "."(저장소 루트)로, dockerfile을 "security-dashboard/Dockerfile"로
# 바꿔야 한다 - 지금은 공용 파일이라 임의로 고치지 않았다 (README.md에도 기록).

FROM python:3.11-slim

WORKDIR /app

COPY security-dashboard/requirements.txt security-dashboard/requirements.txt
RUN pip install --no-cache-dir -r security-dashboard/requirements.txt

COPY schema/ schema/
COPY security-dashboard/ security-dashboard/

ENV MQTT_HOST=mosquitto \
    MQTT_PORT=1883 \
    PORT=3000 \
    MECHDOG_SNAPSHOT_ROOT=/data/snap

EXPOSE 3000

CMD ["python", "-u", "security-dashboard/app/main.py"]
