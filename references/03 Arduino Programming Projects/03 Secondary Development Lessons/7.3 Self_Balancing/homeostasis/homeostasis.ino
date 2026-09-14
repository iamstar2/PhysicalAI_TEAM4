#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//발광 초음파 객체 생성
UltrasoundSonar ult;

uint8_t step = 0;

uint8_t recognize_result = 0;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  ult.Ultrasound_init(); //발광 초음파 모듈 초기화
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  switch (step) {
    case 0:
      // 발광 초음파 색상 설정 함수
      // 매개변수1: 설정할 LED, 0이면 두 LED 모두 설정, 1이면 LED 1 설정, 2이면 LED 2 설정;
      // 매개변수2,3,4: 각각 빨강, 초록, 파랑 색상 값에 해당
      ult.setRGB(0,0xff,0xcc,0x33);
      // 자동 균형(자세 안정화) 상태 켜기
      mechdog.homeostasis(true);
      delay(2000);
      // 아직 자동 균형 상태인지 확인하고, 상태를 벗어나면 이 반복문을 종료합니다
      while (mechdog.read_homeostasis_status()){
        delay(100);
      }
      ult.setRGB(0,0x33,0x33,0xff);
      mechdog.playTone(800, 100, true);
      step++;
    }
}
