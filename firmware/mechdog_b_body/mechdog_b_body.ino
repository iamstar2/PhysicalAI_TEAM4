/*
 * MechDog B 본체 — 센서 브리지 펌웨어 (Wi-Fi + MQTT)
 * ---------------------------------------------------------------------------
 * 역할: 본체(ESP32-WROOM-32D)에 달린 센서 2개의 값을 Wi-Fi/MQTT로 발행한다.
 *   - 터치 센서  -> PTT 트리거          (FR-B-1003, 우선순위 M)
 *   - 초음파 센서 -> 방문자 재실 확인    (FR-B-1001, 우선순위 S)
 * 구독하는 RPi5(게이트 스탠드의 대화 유닛)가 이 값을 받아 STT/TTS 흐름을 제어한다.
 *
 * 왜 UART가 아니라 MQTT인가 (09_작업기록 LOG-22)
 *   본체의 외부 확장 포트는 GPIO 32/33이고, 터치 센서도 GPIO 33을 쓴다
 *   (Hiwonder.h: Touch_Pin 33 / MechDog_uart.ino: txPin 33 / WMMatrixLed tm(32,33)).
 *   즉 UART로 배선하면 터치 PTT와 핀이 물리적으로 겹친다. 무선으로 가면 이 충돌이
 *   아예 없어지고, 배선·커넥터 위치 문제도 사라진다.
 *
 * B는 걷지 않는다 (LOG-09). 그래서 이 펌웨어에는 이동·동작 그룹 코드가 없다.
 * 제스처(FR-B-1002)는 5주 범위에서 제외됐다 (LOG-20).
 *
 * 눈 LED는 범위에 다시 넣었다
 *   방문자가 "지금 말해도 되는지"를 알 방법이 소리밖에 없으면, 시끄러운 물류센터 정문에서는
 *   사실상 알 수 없다. 눈 색으로 상태를 보이면 제스처(동작 그룹) 없이도 해결된다.
 *   **추가 배선이 없다** — 눈 RGB 2개는 초음파 센서 모듈에 달려 있어서(Hiwonder.h),
 *   이미 쓰고 있는 UltrasoundSonar 객체의 setRGB() 로 바로 제어된다.
 *
 * 필요 라이브러리
 *   - WiFi.h        : ESP32 보드 패키지 기본 포함
 *   - PubSubClient  : Arduino 라이브러리 매니저에서 "PubSubClient" (Nick O'Leary) 설치
 *   - Hiwonder 계열 : 이 스케치 폴더에 같이 들어있는 .h/.cpp (벤더 제공)
 *
 * 보드 설정: ESP32 Dev Module, 115200 baud
 */

#include <WiFi.h>
#include <PubSubClient.h>

#include "mech_base_types.h"
#include "HW_MechDog.h"

// ===========================================================================
// 1. 접속 정보 — secrets.h 에서 읽는다 (깃허브에 올라가지 않는 파일)
//    처음 받았다면: cp secrets.example.h secrets.h  후 값 채울 것
// ===========================================================================
#include "secrets.h"

static const char*    WIFI_SSID = SECRET_WIFI_SSID;  // ⚠ 본체 ESP32는 2.4GHz 전용
static const char*    WIFI_PASS = SECRET_WIFI_PASS;
static const char*    MQTT_HOST = SECRET_MQTT_HOST;
static const uint16_t MQTT_PORT = SECRET_MQTT_PORT;
static const char*    MQTT_USER = SECRET_MQTT_USER;  // 비워두면 익명 접속
static const char*    MQTT_PASS = SECRET_MQTT_PASS;

// ===========================================================================
// 2. 토픽
// ---------------------------------------------------------------------------
// 주의: 공용 스키마 네임스페이스(mechdog/v1/#)를 쓰지 않는다.
//   schema/topics.json 의 subscribe_all 이 "mechdog/v1/#" 이고, 공용 메시지는
//   additionalProperties:false 로 엄격히 검증된다. 여기서 보내는 센서값은 공용
//   스키마에 정의된 메시지가 아니므로, v1 네임스페이스에 끼워 넣으면 다른 노드의
//   스키마 검증을 깨뜨린다. 그래서 mechdog/internal/... 로 분리한다.
// ===========================================================================
static const char* TOPIC_TOUCH  = "mechdog/internal/b/touch";
static const char* TOPIC_ULTRA  = "mechdog/internal/b/ultrasonic";
static const char* TOPIC_STATUS = "mechdog/internal/b/status";
// 유일한 구독 토픽. RPi5 의 대화 상태를 받아 눈 색을 바꾼다.
//   {"state":"idle"|"listening"|"thinking"|"speaking"|"error"}
//   {"r":255,"g":200,"b":0}  ← 색 튜닝용 직접 지정 (재업로드 없이 실물 색 맞추기)
static const char* TOPIC_EYE    = "mechdog/internal/b/eye";
static const char* CLIENT_ID    = "mechdog_b_body";
static const char* FW_VERSION   = "b-body-1.1";

// ===========================================================================
// 3. 동작 파라미터
// ===========================================================================
static const uint32_t TOUCH_POLL_MS   = 20;    // 벤더 Button_Task 와 같은 주기
static const uint32_t ULTRA_PERIOD_MS = 300;   // FR-B-1001: 0.3초 주기 폴링
static const uint32_t RECONNECT_MS    = 3000;  // MQTT 재접속 시도 간격
static const uint16_t MQTT_KEEPALIVE_S = 5;    // LWT 가 약 7.5초 안에 뜨도록

// 초음파 유효 범위 (cm). 범위 밖이면 측정 실패로 보고 valid=false 로 보낸다.
//   단위 확인 완료 — Hiwonder.cpp 의 getDistance() 가 `(raw_mm) / 10` 을 돌려주므로 cm 다.
//   측정 실패 시에는 내부적으로 5000mm 를 넣어 **500cm** 가 나온다
//   (`if(distance == DISTANCE_ERRO) distance = 5000;`). 그래서 상한 400 이면 자동으로 걸러진다.
//   FR-B-1001 의 재실 임계 1.5m = 150cm 판정은 RPi5 쪽에서 한다.
static const uint16_t ULTRA_MIN_CM = 1;
static const uint16_t ULTRA_MAX_CM = 400;

// --- 눈 LED ---------------------------------------------------------------
// 눈 RGB 는 초음파 모듈과 **같은 I2C 버스**에 있다. 초음파를 300ms 마다 읽으므로
// LED 를 매 루프 쓰면 버스를 점유해 거리 측정이 밀린다. 25ms 로 제한한다
// (사람 눈에는 40fps 라 충분히 부드럽다).
static const uint32_t EYE_WRITE_MS = 25;

// ===========================================================================
// 4. 전역
// ===========================================================================
// 주의: MechDog 객체를 만들지도, MechDog_init() 을 부르지도 않는다.
//   벤더 예제는 전부 MechDog_init() 을 먼저 부르지만, 그러면 **서보 8개가 기본 자세를
//   계속 유지**하느라 전류를 지속적으로 먹고 다리 모터가 뜨거워진다(실제로 발생, LOG-30).
//   B는 걷지도, 자세를 유지할 필요도 없다(LOG-09/LOG-20). 그리고 Ultrasound_init() 이
//   I2C 버스를 스스로 켜므로(Hiwonder.cpp: IIC1.begin(SDA1,SCL1)) 서보 초기화 없이도
//   초음파·터치가 정상 동작한다.
UltrasoundSonar ult;
Button         btn;
// 부저는 **일부러 만들지 않는다.**
//   저전력 "삐" 알람을 끄려고 PowerBuzzer 를 쓰려 했으나, Buzzer_init() 이 protected 라
//   MechDog_init() 을 통해서만 초기화된다. 우리는 서보 발열 때문에 그걸 부르지 않으므로
//   (LOG-30) **부저 태스크가 아예 뜨지 않는다 → 이 펌웨어는 삐 소리를 낼 수 없다.**
//   즉 알람을 끌 필요 자체가 없다. 전에 들렸던 소리는 벤더 기본 펌웨어 쪽이다.

WiFiClient   net;
PubSubClient mqtt(net);

// --- 눈 LED 상태 기계 -------------------------------------------------------
// 색은 09_작업기록 / B_내일테스트_준비사양.md 에서 확정한 값.
enum EyeState { EYE_IDLE = 0, EYE_LISTENING, EYE_THINKING, EYE_SPEAKING, EYE_ERROR };

struct Rgb { uint8_t r, g, b; };

static const Rgb EYE_COLOR[] = {
  { 255, 200,   0 },   // IDLE      노랑 — 대기
  {   0, 255,   0 },   // LISTENING 초록 — 지금 말하세요
  { 255,  80,   0 },   // THINKING  주황 — 처리 중
  {   0,   0, 255 },   // SPEAKING  파랑 — 안내 중
  { 255,   0,   0 },   // ERROR     빨강 — 재질문/오류
};

// 전이 시간. 듣기 시작은 즉각 반응해야 한다(200ms).
// THINKING 은 아래 왕복이 따로 처리하므로 여기 값은 '진입 블렌딩'에만 쓰인다.
static const uint16_t EYE_FADE_MS[] = { 400, 200, 300, 300, 120 };

// 처리 중에는 **초록 ↔ 주황을 계속 왕복**한다. 고정색이면 멈춘 것처럼 보이는데,
// 실제로는 STT 가 돌고 있어 방문자가 기다려야 하는 구간이다.
//   왕복 1회(초록→주황→초록)에 걸리는 시간. 사인이라 양 끝에서 느려져 흐르듯 보인다.
static const uint32_t EYE_THINK_CYCLE_MS = 2000;
//   직전 색에서 왕복 궤도로 부드럽게 올라타는 시간. 이게 없으면 진입 순간 색이 튄다.
static const uint32_t EYE_THINK_ENTER_MS = 300;

static EyeState eyeState     = EYE_IDLE;
static Rgb      eyeFrom      = { 255, 200, 0 };   // 페이드 시작색(현재 보이는 색)
static uint32_t eyeFadeT0    = 0;
static uint16_t eyeFadeMs    = 0;
static uint32_t lastEyeWrite = 0;
static Rgb      eyeShown     = { 0, 0, 0 };       // 마지막으로 실제 기록한 값
static bool     eyeManual    = false;             // 직접 색 지정 모드(튜닝용)

static bool     lastTouch      = false;
static bool     touchEverSent  = false;
static uint32_t seqTouch       = 0;
static uint32_t seqUltra       = 0;
static uint32_t lastTouchPoll  = 0;
static uint32_t lastUltraPoll  = 0;
static uint32_t lastReconnect  = 0;

// ===========================================================================
// 5. 발행 헬퍼
// ===========================================================================
static void publishTouch(bool pressed) {
  char payload[96];
  snprintf(payload, sizeof(payload),
           "{\"seq\":%lu,\"uptime_ms\":%lu,\"touch\":%s}",
           (unsigned long)(++seqTouch), (unsigned long)millis(),
           pressed ? "true" : "false");

  // QoS 1 상당(PubSubClient 는 QoS 0 발행만 지원) + retain true.
  //   retain 을 켜두는 이유: RPi5 가 재시작하면 마지막 터치 상태를 즉시 알아야
  //   청취 창(PTT)이 열려 있는지 판단할 수 있다.
  mqtt.publish(TOPIC_TOUCH, payload, true);
  Serial.printf("[touch] %s\n", payload);
}

static void publishUltra(uint16_t cm) {
  const bool valid = (cm >= ULTRA_MIN_CM && cm <= ULTRA_MAX_CM);
  char payload[128];
  snprintf(payload, sizeof(payload),
           "{\"seq\":%lu,\"uptime_ms\":%lu,\"distance_cm\":%u,\"valid\":%s}",
           (unsigned long)(++seqUltra), (unsigned long)millis(),
           (unsigned)cm, valid ? "true" : "false");

  // 주기 스트림이라 retain true — 새로 붙은 RPi5 가 최신값을 바로 받는다.
  mqtt.publish(TOPIC_ULTRA, payload, true);
}

static void publishOnline(bool online) {
  char payload[96];
  snprintf(payload, sizeof(payload),
           "{\"online\":%s,\"fw\":\"%s\",\"uptime_ms\":%lu}",
           online ? "true" : "false", FW_VERSION, (unsigned long)millis());
  mqtt.publish(TOPIC_STATUS, payload, true);
}

// ===========================================================================
// 5-b. 눈 LED
// ---------------------------------------------------------------------------
// 전부 논블로킹이다. 페이드를 delay() 로 돌리면 그 사이 mqtt.loop() 가 멈춰
// 터치 발행이 밀리고, keepalive 5초를 놓쳐 LWT 가 잘못 뜬다.
// ===========================================================================
static void writeEye(const Rgb& c) {
  if (c.r == eyeShown.r && c.g == eyeShown.g && c.b == eyeShown.b) return;
  eyeShown = c;
  ult.setRGB(0, c.r, c.g, c.b);   // 왼눈
  ult.setRGB(1, c.r, c.g, c.b);   // 오른눈
}

static Rgb lerpRgb(const Rgb& a, const Rgb& b, float t) {
  Rgb c;
  c.r = (uint8_t)(a.r + (b.r - a.r) * t);
  c.g = (uint8_t)(a.g + (b.g - a.g) * t);
  c.b = (uint8_t)(a.b + (b.b - a.b) * t);
  return c;
}

static Rgb eyeCurrent() {
  const Rgb& to = EYE_COLOR[eyeState];
  if (eyeFadeMs == 0) return to;

  const uint32_t el = millis() - eyeFadeT0;
  if (el >= eyeFadeMs) return to;

  // 선형 보간. 한 스텝이 25ms 라 800ms 전이는 32단계 — 눈으로는 연속으로 보인다.
  const float t = (float)el / (float)eyeFadeMs;
  Rgb c;
  c.r = (uint8_t)(eyeFrom.r + (to.r - eyeFrom.r) * t);
  c.g = (uint8_t)(eyeFrom.g + (to.g - eyeFrom.g) * t);
  c.b = (uint8_t)(eyeFrom.b + (to.b - eyeFrom.b) * t);
  return c;
}

static void setEyeState(EyeState s) {
  if (s == eyeState && !eyeManual) return;   // 같은 상태 재수신 시 왕복을 끊지 않는다
  // '지금 실제로 켜져 있는 색'에서 이어간다. eyeCurrent() 를 쓰면 THINKING 왕복 중일 때
  // 페이드 계산값(주황)을 집어와서 색이 튄다.
  eyeFrom   = eyeShown;
  eyeState  = s;
  eyeFadeT0 = millis();
  eyeFadeMs = EYE_FADE_MS[s];
  eyeManual = false;
}

static void updateEye() {
  if (eyeManual) return;         // 직접 지정 모드에서는 상태 기계가 손대지 않는다

  const uint32_t now = millis();
  if (now - lastEyeWrite < EYE_WRITE_MS) return;
  lastEyeWrite = now;

  Rgb c;
  if (eyeState == EYE_THINKING) {
    // 초록 ↔ 주황 왕복. cos 를 쓰면 t 가 0→1→0 으로 부드럽게 오가고,
    // 양 끝(초록/주황)에서 변화가 느려져 "숨 쉬듯" 보인다.
    const uint32_t el = now - eyeFadeT0;
    const float ph = (float)(el % EYE_THINK_CYCLE_MS) / (float)EYE_THINK_CYCLE_MS;
    const float t  = 0.5f - 0.5f * cosf(ph * TWO_PI);
    c = lerpRgb(EYE_COLOR[EYE_LISTENING], EYE_COLOR[EYE_THINKING], t);

    // 진입 순간에는 직전 색에서 궤도로 끌어올린다(초록에서 넘어오면 t=0 이라 티가 안 난다).
    if (el < EYE_THINK_ENTER_MS) {
      c = lerpRgb(eyeFrom, c, (float)el / (float)EYE_THINK_ENTER_MS);
    }
  } else {
    c = eyeCurrent();
  }
  writeEye(c);
}

// MQTT 로 받은 상태를 눈에 반영한다. PubSubClient 의 payload 는 널 종료가 아니다.
static void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  char buf[128];
  const unsigned int n = (len < sizeof(buf) - 1) ? len : sizeof(buf) - 1;
  memcpy(buf, payload, n);
  buf[n] = '\0';

  if (strcmp(topic, TOPIC_EYE) != 0) return;
  Serial.printf("[eye] %s\n", buf);

  // 색 직접 지정이 오면 그대로 쓴다. 내일 실물에서 노랑/주황이 구분되는지 보고
  // 재업로드 없이 값을 맞추기 위한 경로다.
  const char* pr = strstr(buf, "\"r\"");
  if (pr) {
    int r = 0, g = 0, b = 0;
    const char* pg = strstr(buf, "\"g\"");
    const char* pb = strstr(buf, "\"b\"");
    if (pg && pb) {
      r = atoi(strchr(pr, ':') + 1);
      g = atoi(strchr(pg, ':') + 1);
      b = atoi(strchr(pb, ':') + 1);
      eyeManual = true;
      eyeFadeMs = 0;
      writeEye({ (uint8_t)constrain(r, 0, 255),
                 (uint8_t)constrain(g, 0, 255),
                 (uint8_t)constrain(b, 0, 255) });
      return;
    }
  }

  if      (strstr(buf, "listening")) setEyeState(EYE_LISTENING);
  else if (strstr(buf, "thinking"))  setEyeState(EYE_THINKING);
  else if (strstr(buf, "speaking"))  setEyeState(EYE_SPEAKING);
  else if (strstr(buf, "error"))     setEyeState(EYE_ERROR);
  else if (strstr(buf, "idle"))      setEyeState(EYE_IDLE);
}

// ===========================================================================
// 6. 연결 관리
// ===========================================================================
static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  static uint32_t lastTry = 0;
  const uint32_t now = millis();
  if (now - lastTry < RECONNECT_MS) return;
  lastTry = now;

  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

static void ensureMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connected()) return;

  const uint32_t now = millis();
  if (now - lastReconnect < RECONNECT_MS) return;
  lastReconnect = now;

  Serial.printf("[mqtt] connecting to %s:%u ...\n", MQTT_HOST, MQTT_PORT);

  // LWT(유언). 본체가 죽거나 Wi-Fi 가 끊기면 브로커가 이 메시지를 대신 발행한다.
  //   FR-B-1005(본체 링크 감시)를 별도 하트비트 없이 이걸로 대체한다.
  //   RPi5 는 online=false 를 받으면 PTT 모드를 VAD 모드로 폴백하면 된다 (AC-1005-2).
  char lwt[96];
  snprintf(lwt, sizeof(lwt),
           "{\"online\":false,\"fw\":\"%s\"}", FW_VERSION);

  bool ok;
  if (strlen(MQTT_USER) > 0) {
    ok = mqtt.connect(CLIENT_ID, MQTT_USER, MQTT_PASS,
                      TOPIC_STATUS, 0, true, lwt);
  } else {
    ok = mqtt.connect(CLIENT_ID, TOPIC_STATUS, 0, true, lwt);
  }

  if (ok) {
    Serial.println("[mqtt] connected");
    mqtt.subscribe(TOPIC_EYE);
    publishOnline(true);
    // 재접속 직후 현재 터치 상태를 한 번 다시 보내 RPi5 와 상태를 맞춘다.
    publishTouch(lastTouch);
  } else {
    Serial.printf("[mqtt] failed, rc=%d\n", mqtt.state());
  }
}

// ===========================================================================
// 7. 센서 폴링
// ===========================================================================
static void pollTouch() {
  const uint32_t now = millis();
  if (now - lastTouchPoll < TOUCH_POLL_MS) return;
  lastTouchPoll = now;

  // Button 클래스(Button_init(2) = 터치 모드)는 내부 FreeRTOS 태스크가 20ms 주기로
  // 폴링하며 디바운스까지 해준다. GetButtonResult() 는 "지금 눌려있는지"를 돌려준다
  // (Hiwonder.cpp Button_Task: 눌림 3틱 이상이면 true, 떼면 false).
  const bool pressed = (btn.GetButtonResult() != 0);

  if (!touchEverSent || pressed != lastTouch) {
    lastTouch = pressed;
    touchEverSent = true;
    if (mqtt.connected()) publishTouch(pressed);
  }
}

static void pollUltra() {
  const uint32_t now = millis();
  if (now - lastUltraPoll < ULTRA_PERIOD_MS) return;
  lastUltraPoll = now;

  const uint16_t cm = ult.getDistance();
  if (mqtt.connected()) publishUltra(cm);
}

// ===========================================================================
// 8. setup / loop
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\n=== MechDog B body sensor bridge (%s) ===\n", FW_VERSION);

  // 센서만 올린다. 서보 드라이버는 건드리지 않아 모터에 전류가 흐르지 않는다
  // (신호를 안 주면 서보는 힘을 안 쓰고 늘어져 있는다 → 발열 없음).
  ult.Ultrasound_init();     // 초음파(I2C) — 자체적으로 IIC1.begin() 수행
  btn.Button_init(2);        // 2 = 터치 센서 모드 (GPIO 33)

  // 안내음·효과음(띠링)은 전부 RPi5 의 USB 스피커로 내보낸다. 본체 부저는 쓰지 않는다.
  Serial.println("[init] sensors ready (servo 미기동 — 발열 방지, 부저 미사용)");

  // 대기색(노랑)을 즉시 켠다. 전원이 들어왔는데 눈이 꺼져 있으면 고장으로 보인다.
  eyeFadeMs = 0;
  writeEye(EYE_COLOR[EYE_IDLE]);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);      // 절전으로 인한 응답 지연 방지 (PTT 반응성)
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);

  ensureWifi();
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();

  pollTouch();
  pollUltra();
  updateEye();
}
