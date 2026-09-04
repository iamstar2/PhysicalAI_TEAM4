#include "mech_base_types.h"
#include "HW_MechDog.h"

MechDog mechdog;
//밝기 센서 객체 생성
LightSensor light;

//조도(밝기) 임계값
uint16_t Intensity_threshold = 100;
//읽어온 밝기 값
uint16_t brightness = 0;

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
  //조도 읽기
  brightness = light.read();
  //밝기 값이 임계값보다 크면
  if(brightness >= Intensity_threshold){
    //서기 동작 실행
    //mechdog.action_run("stand_four_legs");
    mechdog.set_default_pose();
    delay(2000);
    //걷기
    mechdog.move(80,0);
    delay(1000);
    //밝기 값이 임계값보다 큰 동안 계속 대기하다가, 임계값보다 작아지면 반복문을 빠져나갑니다.
    while(light.read() > Intensity_threshold){
      delay(100);
    }
  }else{
    //정지
    mechdog.move(0,0);
    delay(2000);
    //엎드리기 동작 그룹 실행
    mechdog.action_run("go_prone");
    delay(1000);
    //밝기 값이 임계값보다 작은 동안 계속 대기하다가, 임계값보다 커지면 반복문을 빠져나갑니다.
    while(light.read() < Intensity_threshold){
      delay(100);
    }
  }
}