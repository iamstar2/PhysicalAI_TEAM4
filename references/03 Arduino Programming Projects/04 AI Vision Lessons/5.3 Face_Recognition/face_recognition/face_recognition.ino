#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//ESP32S3 비전 모듈 객체 생성
ESP32S3Cam cam;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  cam.ESP32S3_init(); //ESP32S3 비전 모듈 초기화
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  // RED \ YELLOW \ GREEN \ BLUE \ BLACK
  /*
    face_recognition() 함수:
    얼굴이 인식되면 true를 반환하고, 그렇지 않으면 false를 반환합니다
  */
  if(cam.face_recognition()){
    mechdog.action_run("scrape_a_bow");
    delay(5000);
  }
  delay(100);
}
