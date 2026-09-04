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
  mech_pose_t roll[2] = {
    {{0,0,0},{15,0,0}},
    {{0,0,0},{-30,0,0}}
  };
  mech_pose_t pitch[2] = {
    {{0,0,0},{0,15,0}},
    {{0,0,0},{0,-30,0}}
  };
  /*
       transform() 자세 변환 함수
       매개변수1: 몸체 평행이동(x,y,z축), 몸체 회전(x,y,z축 기준 회전)
       매개변수2: 변환에 걸리는 시간
  */
  switch (step) {
    case 0:
      mechdog.transform(roll[0],500); //X축 기준 회전
      delay(2000);
      mechdog.transform(roll[1],1000);
      delay(2000);
      mechdog.set_default_pose();
      delay(2000);
      step++;
      break;
    case 1:
      mechdog.transform(pitch[0],500); //Y축 기준 회전
      delay(2000);
      mechdog.transform(pitch[1],1000);
      delay(2000);
      mechdog.set_default_pose();
      delay(2000);
      step++;
      break;
  }
  delay(100);
}