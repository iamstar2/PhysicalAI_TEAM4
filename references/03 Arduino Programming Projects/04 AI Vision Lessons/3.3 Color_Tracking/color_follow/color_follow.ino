#include "mech_base_types.h"
#include "HW_MechDog.h"

//MechDog 객체 생성
MechDog mechdog;
//ESP32S3 비전 모듈 객체 생성
ESP32S3Cam cam;

int8_t angle = 0;
int8_t dir = 1;
int16_t wide;
int16_t high;
int16_t area;

uint8_t color_data[7]; //비전 모듈이 반환하는 색상 데이터를 저장하는 데 사용

mech_pose_t pose = {
  {-5,0,0},{0,0,0}
};

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화
  cam.ESP32S3_init(); //ESP32S3 비전 모듈 초기화
  delay(1000);
  mechdog.set_gait_params(150,450,40); //보행 파라미터 설정
  mechdog.transform(pose,80); //무게중심을 뒤로 이동
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  // RED \ YELLOW \ GREEN \ BLUE \ BLACK
  /*
    매개변수1: 인식할 색상을 설정
    매개변수2: 인식된 데이터를 수신
  */
  cam.color_follow(GREEN,color_data); //색상 데이터 읽기
  if(color_data[0] == GREEN){
    if(color_data[5] < 60){
      angle = 25;
    }else if(color_data[5] > 100){
      angle = -25;
    }

    if(color_data[6] < 70){
      dir = 1;
    }else{
      dir = -1;
    }
    
    //색상 영역의 면적 계산
    wide = color_data[3] - color_data[1];
    high = color_data[4] - color_data[2];
    area = wide * high;

    if(area > 5000){
      mechdog.move(0,0);
    }else{
      if(dir == 1){
        mechdog.move(50,angle);
      }else{
        mechdog.move(-50,0);
      }
    }

  }else{
    mechdog.move(0,0);
  }
  delay(100);
}
