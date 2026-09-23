// 템플릿 — 이 파일을 secrets.h 로 복사한 뒤 본인 환경 값으로 채운다.
//   cp secrets.example.h secrets.h
// secrets.h 는 .gitignore 에 등록되어 커밋되지 않는다.
#pragma once

// ⚠ 본체 ESP32-WROOM-32D 는 2.4GHz 전용이다.
//   5GHz SSID(예: ..._5G_...)를 넣으면 시리얼 로그에 "[wifi] connecting..." 만 무한 반복된다.
#define SECRET_WIFI_SSID "여기에_2.4GHz_SSID"
#define SECRET_WIFI_PASS "여기에_WIFI_비밀번호"

// MQTT 브로커(host1, docker-compose.host1.yml 의 mosquitto) 주소.
#define SECRET_MQTT_HOST "192.168.0.10"
#define SECRET_MQTT_PORT 1883

// 브로커에 인증을 걸었을 때만 채운다. 비워두면 익명 접속.
#define SECRET_MQTT_USER ""
#define SECRET_MQTT_PASS ""
