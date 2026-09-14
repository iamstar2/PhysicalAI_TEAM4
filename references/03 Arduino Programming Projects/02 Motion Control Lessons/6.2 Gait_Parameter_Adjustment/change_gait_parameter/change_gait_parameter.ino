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
      set_gait_params() 함수
      보행 파라미터를 설정합니다. 매개변수 내용은 다음과 같습니다:
      매개변수1: 발끝이 지면에서 떨어져 있는 시간;
      매개변수2: 발끝이 지면에 닿아 있는 시간;
      매개변수3: 다리를 들어올리는 높이.
  */
  switch (step) {
    case 0:
      mechdog.set_gait_params(150,350,20);
      mechdog.move(50,0);
      delay(5000);
      step++;
      break;
    case 1:
      mechdog.set_gait_params(200,600,50);
      mechdog.move(50,0);
      delay(5000);
      step++;
      break;
  }
  mechdog.move(0,0);
  delay(3000);
}