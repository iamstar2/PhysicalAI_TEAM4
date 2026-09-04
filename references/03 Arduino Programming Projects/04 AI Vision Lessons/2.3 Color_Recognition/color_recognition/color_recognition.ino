#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//발광 초음파 객체 생성
UltrasoundSonar ult;
//ESP32S3 비전 모듈 객체 생성
ESP32S3Cam cam;

uint8_t color[5]; //비전 모듈이 반환하는 색상 데이터를 저장하는 데 사용

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  ult.Ultrasound_init(); //발광 초음파 모듈 초기화
  cam.ESP32S3_init(); //ESP32S3 비전 모듈 초기화
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  cam.color_recognition(color);
  for(int i = 0; i < 5; i++){
    if(color[i] == RED){  //빨간색 인식됨
      ult.setRGB(0,255,0,0);
    }else if(color[i] == GREEN){ //초록색 인식됨
      ult.setRGB(0,0,255,0);
    }else if(color[i] == BLUE){ //파란색 인식됨
      ult.setRGB(0,0,0,255);
    }
  }
  delay(100);
}
