#include "mech_base_types.h"
#include "HW_MechDog.h"

int8_t step = 0;

MechDog mechdog;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  /*
     move() 함수
     매개변수1: 보폭(단위 mm)(양수는 전진, 음수는 후진);
     매개변수2: 회전 각도(단위: 도), 양수는 좌회전, 음수는 우회전
  */
  switch (step) {
    case 0:
      mechdog.move(50,20); //좌회전
      delay(5000);
      mechdog.move(0,0);
      delay(2000);
      mechdog.move(50,-20); //우회전
      delay(5000);
      mechdog.move(0,0); //정지
      delay(2000);
      step++;
      break;
  }
  delay(100);
}