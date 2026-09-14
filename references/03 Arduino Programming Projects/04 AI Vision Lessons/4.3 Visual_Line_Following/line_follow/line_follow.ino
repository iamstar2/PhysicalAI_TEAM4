#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//발광 초음파 모듈 객체 생성
UltrasoundSonar ult;
//ESP32S3 비전 모듈 객체 생성
ESP32S3Cam cam;

uint8_t line_data[14]; //라인트레이싱 데이터를 저장하는 데 사용
uint8_t centerX;

uint8_t last_centerX; //마지막으로 인식된 좌표를 저장하는 데 사용

mech_pose_t pose = {
  {-5,0,0},{0,0,0}
};


void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  ult.Ultrasound_init(); //발광 초음파 모듈 초기화
  cam.ESP32S3_init(); //ESP32S3 비전 모듈 초기화
  delay(1000);
  ult.setRGB(0,0x00,0x00,0x00); //발광 초음파의 RGB 조명 끄기
  mechdog.set_gait_params(150,450,40); //보행 파라미터 설정
  mechdog.transform(pose,80); //무게중심을 뒤로 이동
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  /*
    line_follow() 함수
    매개변수1: 라인트레이싱할 색상을 설정
    매개변수2: 라인 데이터를 저장할 배열, 이 배열의 길이는 최소 14 이상이어야 함
  */
  cam.line_follow(YELLOW,line_data);
  if(line_data[0] == YELLOW){ //설정한 색상이 인식되면
    centerX = line_data[1]; //라인의 중심점 가져오기
    if(centerX < 70){ //좌회전
      mechdog.move(80,35);
      last_centerX = centerX; //마지막으로 인식된 좌표 저장
    }else if(centerX > 110){ //우회전
      mechdog.move(80, -35);
      last_centerX = centerX; //마지막으로 인식된 좌표 저장
    }
  }else if(last_centerX < 100 && last_centerX != 0){ //라인이 인식되지 않을 때 라인 이탈 보정 수행
    mechdog.move(80, 35);
    last_centerX = 0;
    delay(500);
  }else if(last_centerX > 100){ 
    mechdog.move(80, -35);
    last_centerX = 0;
    delay(500);
  }else{
    mechdog.move(80,0);
  }
  delay(10);
}
