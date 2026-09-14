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
     action_run() 함수
     매개변수: 실행할 동작 그룹의 이름. 자세한 내용은 본 절의 문서를 참고하세요
  */
  switch (step) {
    case 0:
      mechdog.action_run("left_foot_kick"); //왼발 킥 동작 그룹 실행
      delay(3000);
      step++;
      break;
  }
  delay(100);
}