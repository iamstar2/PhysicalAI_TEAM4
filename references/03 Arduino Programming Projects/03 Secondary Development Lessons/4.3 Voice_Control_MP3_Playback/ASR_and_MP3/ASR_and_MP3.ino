#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//음성 인식 모듈 객체 생성
ASRSensor myasr;
//MP3 모듈 객체 생성
MP3Sensor mp3;

uint8_t recognize_result = 0;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  myasr.ASR_init(); //음성 인식 모듈 초기화
  mp3.MP3_init(); //MP3 모듈 객체 초기화
  delay(1000);

  //반복 인식 모드로 설정
  myasr.setMode(1);
  //MP3 볼륨을 30으로 설정
  mp3.volume(30);

  if(true){ //음성 인식 명령어 등록. 한 번만 설정하면 되며, 이후에는 False로 바꿔도 됩니다
    myasr.addWord(0,"ni hao");
    myasr.addWord(1,"xiang qian");
    myasr.addWord(2,"xiang hou");
    myasr.addWord(3,"xiang zuo");
    myasr.addWord(4,"xiang you");
    myasr.addWord(5,"ting zhi");
  }
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  recognize_result = myasr.getResult();
  //전진 명령 인식됨
  if(recognize_result == 1){
    Serial.println(recognize_result);
    mp3.play(1);
    mp3.play();
    mechdog.move(80,0);
    delay(3000);
    mechdog.move(0,0);
    delay(2000);
  }
  //후진 명령 인식됨
  if(recognize_result == 2){
    Serial.println(recognize_result);
    mp3.play(2);
    mp3.play();
    mechdog.move(-80,0);
    delay(3000);
    mechdog.move(0,0);
    delay(2000);
  }
  //좌회전 명령 인식됨
  if(recognize_result == 3){
    Serial.println(recognize_result);
    mp3.play(3);
    mp3.play();
    mechdog.move(80,30);
    delay(3000);
    mechdog.move(0,0);
    delay(2000);
  }
  //우회전 명령 인식됨
  if(recognize_result == 4){
    Serial.println(recognize_result);
    mp3.play(1);
    mp3.play();
    mechdog.move(80,-30);
    delay(3000);
    mechdog.move(0,0);
    delay(2000);
  }
  delay(50);
}
