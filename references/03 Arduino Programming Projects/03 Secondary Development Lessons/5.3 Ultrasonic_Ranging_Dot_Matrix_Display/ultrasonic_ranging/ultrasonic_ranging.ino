#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//발광 초음파 센서 객체 생성
UltrasoundSonar ult;
//LED 도트 매트릭스 모듈 객체 생성
WMMatrixLed tm(32,33);
//초음파로 측정한 거리
uint16_t distance = 0;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  ult.Ultrasound_init(); //발광 초음파 초기화

  tm.setBrightness(4); //밝기 설정
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  //발광 초음파로 측정한 거리 가져오기
  distance = ult.getDistance();
  //도트 매트릭스 모듈에 거리 표시
  tm.showNum((float)distance,0);
  //Serial.println(distance);
  //거리가 15mm보다 작으면
  if(distance <= 15){
    //발광 초음파 색상 설정 함수
    //매개변수1: 설정할 LED, 0이면 두 LED 모두 설정, 1이면 LED 1 설정, 2이면 LED 2 설정;
    //매개변수2,3,4: 각각 빨강, 초록, 파랑 색상 값에 해당
    ult.setRGB(0,0xff,0x00,0x00); //빨간색으로 설정
   }
   else{
    if(distance > 30){
      ult.setRGB(0,0x00,0x00,0x99); //파란색으로 설정
    }else{
      ult.setRGB(0,0xfd,0xd0,0x00); //노란색으로 설정
    }
  }
  delay(100);
}
