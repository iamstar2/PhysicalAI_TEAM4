// 터치센서 단독 진단용 — GPIO33(Touch_Pin) 상태를 그대로 시리얼에 찍는다.
// Button 클래스(디바운스 포함)와 순수 digitalRead 둘 다 같이 찍어서
// 라이브러리 로직 문제인지, 핀 자체 문제인지 구분한다.
#include "mech_base_types.h"
#include "HW_MechDog.h"

Button btn;
#define RAW_PIN 33

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Touch sensor 단독 테스트 ===");
  pinMode(RAW_PIN, INPUT_PULLUP);
  btn.Button_init(2);  // 2 = 터치 모드 (Touch_Pin = GPIO33)
  Serial.println("init done");
}

void loop() {
  int raw = digitalRead(RAW_PIN);
  int lib = btn.GetButtonResult();
  Serial.printf("raw_digitalRead(33)=%d  Button.GetButtonResult()=%d\n", raw, lib);
  delay(200);
}
