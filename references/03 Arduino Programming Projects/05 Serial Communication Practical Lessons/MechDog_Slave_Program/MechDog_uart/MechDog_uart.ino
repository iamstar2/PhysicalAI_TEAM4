#include "mech_base_types.h"
#include "HW_MechDog.h"
#define rxPin 32
#define txPin 33

typedef struct Object{
  MechDog* mechdog;
  UltrasoundSonar* ult;
};
extern MPU6050 accelgyro;

MechDog mechdog; //MechDog 객체 생성
UltrasoundSonar ult; //발광 초음파 객체 생성

Object obj;

HardwareSerial mySerial(1); //시리얼 포트 인스턴스 생성

mech_pose_t attitude[8] = {
  {{10,0,0},{0,0,0}}, //무게중심을 앞으로 이동한 자세
  {{-10,0,0},{0,0,0}}, //무게중심을 뒤로 이동한 자세
  {{0,0,0},{1,0,0}}, //Roll +
  {{0,0,0},{-1,0,0}}, //Roll -
  {{0,0,0},{0,1,0}}, //Pitch +
  {{0,0,0},{0,-1,0}}, //Pitch -
  {{0,0,1},{0,0,0}}, //High +
  {{0,0,-1},{0,0,0}}, //High -
};



static void run_task(void *p); //동작 실행 작업

int8_t step = 0;
int8_t avo_flg = -1; //장애물 회피 플래그
int8_t forward_flag = 1; //장애물 회피 자세 전환 플래그
int8_t action_num = -1; //이동 동작
int8_t dir_flag = 1; //이동 자세 전환 플래그
int8_t actions = 0; //동작 그룹
int8_t actions_flg = 0; //동작 그룹 실행 플래그
int8_t attitude_flg = 0; //자세 조정 플래그
int8_t homeostasis_flg = 0; //자동 균형(자세 안정화) 기능

//자세 조정 각도
int8_t Pitch_angle = 0;
int8_t Roll_angle = 0;
int8_t High_mm = 0;

int8_t rec_data[3];

void setup() {
  mySerial.begin(9600,SERIAL_8N1,rxPin,txPin); //시리얼 포트 초기화
  obj.mechdog = &mechdog;
  obj.ult = &ult;
  Project_init(); //MechDog 및 발광 초음파 모듈 초기화
  delay(100);
}

void loop() {
  uint8_t index = 0;
  while (mySerial.available() > 0) {
    String cmd = mySerial.readString(); //시리얼 데이터 읽기
    if(cmd.startsWith("CMD") && cmd.endsWith("$")){ //데이터 유효성 검사
      cmd = cmd.substring(cmd.indexOf('|') + 1,cmd.indexOf('$'));
      while(cmd.indexOf("|") != -1){
        rec_data[index] = cmd.substring(0, cmd.indexOf('|')).toInt(); //데이터 문자열을 추출하여 int형으로 변환
        cmd = cmd.substring(cmd.indexOf('|') + 1);
        index++;
      }
      switch(rec_data[0]){
        case 1: //자세 조정
          if(index == 2 && rec_data[1] == 5){
            mechdog.set_default_pose();
            vTaskDelay(1000);
          }else if(index == 3){
            switch(rec_data[1]){
              case 1: //Pitch 조정
                if(abs(rec_data[2]) == 1){
                  if(rec_data[2] == 1 && Pitch_angle < 17){
                    Pitch_angle++;
                    mechdog.transform(attitude[4],80);
                  }else if(rec_data[2] == -1 && Pitch_angle > -17){
                    Pitch_angle--;
                    mechdog.transform(attitude[5],80);
                  }
                }
                break;
              case 2: //Roll 조정
                if(abs(rec_data[2]) == 1){
                  if(rec_data[2] == 1 && Roll_angle < 17){
                    Roll_angle++;
                    mechdog.transform(attitude[2],80);
                  }else if(rec_data[2] == -1 && Roll_angle > -17){
                    Roll_angle--;
                    mechdog.transform(attitude[3],80);
                  }
                }
                break;
              case 3: //자동 균형
                if(rec_data[2] == 1){
                  homeostasis_flg = 1;
                }else{
                  homeostasis_flg = 0;
                }
                break;
              case 4: //Roll 조정
                if(abs(rec_data[2]) == 1){
                  if(rec_data[2] == 1 && High_mm < 15){
                    High_mm++;
                    mechdog.transform(attitude[6],80);
                  }else if(rec_data[2] == -1 && High_mm > -25){
                    High_mm--;
                    mechdog.transform(attitude[7],80);
                  }
                }
                break;
            }
          }
          break;

        case 2: //동작 그룹 호출
          if(index == 3){
            if(rec_data[1] == 1){
              actions_flg = 1;
              actions = rec_data[2];
            }else if(rec_data[1] == 2){
              actions_flg = 2;
              actions = rec_data[2];
            }
          }
          break;

        case 3: //이동 제어
          if(index == 2){
            action_num = rec_data[1];
            if(action_num < 6 && dir_flag != 1){
              dir_flag = 1;
              mechdog.transform(attitude[0],100);
            }else{
              dir_flag = -1;
              mechdog.transform(attitude[1],100);
            }
          }
          break;

        case 4: //초음파 데이터
          if(index == 2 && rec_data[1] == 1){
            mySerial.printf("CMD|%d|%d|$",rec_data[0],ult.getDistance()*10); //초음파 데이터 읽기
          }else if(index == 3){
            if(rec_data[1] == 2){
              if(rec_data[2] == 1){
                avo_flg = 1;
              }else if(rec_data[2] == 0){
                avo_flg= 0;
              }
            }
          }
          break;

        case 5: //IMU 데이터
          if(index == 1){
            IMU_init(); //IMU 초기화
            delay(100);
            read_angle(); //PITCH, ROLL 각도 읽기
            mySerial.printf("CMD|%d|%f|%f|$",rec_data[0],radianY_last,radianX_last);
          }
          break;

        case 6: //배터리 잔량
          if(index == 1){
            mySerial.printf("CMD|%d|%d|$",rec_data[0],mechdog.readBattery()); //배터리 잔량 읽기
          }
          break;
      }
    }
  }
  delay(10);
}

void IMU_init(){
  IIC1.begin(SDA1,SCL1);
  accelgyro.initialize();
  accelgyro.setFullScaleGyroRange(3); //각속도 측정 범위 설정
  accelgyro.setFullScaleAccelRange(1); //가속도 측정 범위 설정
}

void Project_init(){
  mechdog.MechDog_init(); //MechDog 초기화
  ult.Ultrasound_init(); //발광 초음파 모듈 초기화

  xTaskCreate( //MechDog 기능 작업 생성
    run_task,
    "runTask",
    2048,
    (void *)&obj,
    1,
    NULL
  );

}

static void run_task(void *p){
  Object *self = (Object *)p;
  MechDog *dog = self->mechdog;
  UltrasoundSonar *u = self->ult;

  while(true){
    if(avo_flg == 1){ //초음파 장애물 회피
      while(true){
        action_num = -1;
        actions_flg = 0;
        if(avo_flg == 0){ //정지
          dog->move(0,0);
          vTaskDelay(20);
          u->setRGB(0,0x33,0x33,0xff);
          avo_flg = -1;
          if(forward_flag == 0){
            forward_flag = 1;
            dog->transform(attitude[0],100);
          }
          vTaskDelay(1000);
          break;
        }
        if(u->getDistance() < 10){ //후진
          if(forward_flag == 1){
            forward_flag = 0;
            dog->transform(attitude[1],100);
          }
          u->setRGB(0,0xff,0x00,0x00);
          dog->move(-40,0);
          for(int i = 0; i <30; i++){
            if(avo_flg == 0){
              break;
            }
            vTaskDelay(100);
          }
        }else if(u->getDistance() < 40){ //방향 전환
          if(forward_flag == 0){
            forward_flag = 1;
            dog->transform(attitude[0],100);
          }
          u->setRGB(0,0xff,0xcc,0x00);
          dog->move(100,-50);
          for(int i = 0; i <30; i++){
            if(avo_flg == 0){
              break;
            }
            vTaskDelay(100);
          }
        }else{
          u->setRGB(0,0xcc,0x33,0xcc); //전진
          dog->move(120,0);
          vTaskDelay(20);
        }
      }
    }else if(action_num != -1){
      avo_flg = 0;
      actions_flg = 0;
      switch(action_num){
        case 0:
          dog->move(0,0); //정지
          action_num = -1;
          vTaskDelay(20);
          break;
        case 1:
          dog->move(90,-25); //작은 각도로 우측 앞으로 회전
          vTaskDelay(20);
          continue;
        case 2:
          dog->move(80,-40); //큰 각도로 우측 앞으로 회전
          vTaskDelay(20);
          continue;
        case 3:
          dog->move(120,0); //직선 전진
          vTaskDelay(20);
          continue;
        case 4:
          dog->move(80,40); //큰 각도로 좌회전
          vTaskDelay(20);
          continue;
        case 5:
          dog->move(90,25); //작은 각도로 좌회전
          vTaskDelay(20);
          continue;
        case 6:
          dog->move(-40,-20); //좌측으로 후진
          vTaskDelay(20);
          continue;
        case 7:
          dog->move(-40,0); //직선 후진
          vTaskDelay(20);
          continue;
        case 8:
          dog->move(-40,20); //우측으로 후진
          vTaskDelay(20);
          continue;
      }
    }else if(actions_flg != 0){
      action_num = -1;
      avo_flg = 0;

      if(actions_flg == 1){
        switch(actions){
          case 1:
            dog->action_run("left_foot_kick"); //왼발 킥
            vTaskDelay(3000);
            break;
          case 2:
            dog->action_run("right_foot_kick"); //오른발 킥
            vTaskDelay(3000);
            break;
          case 3:
            dog->action_run("stand_four_legs"); //네 발로 서기
            vTaskDelay(3000);
            break;
          case 4:
            dog->action_run("sit_dowm"); //앉기
            vTaskDelay(3000);
            break;
          case 5:
            dog->action_run("go_prone"); //엎드리기
            vTaskDelay(3000);
            break;
          case 6:
            dog->action_run("stand_two_legs"); //두 발로 서기
            vTaskDelay(3000);
            break;
          case 7:
            dog->action_run("handshake"); //악수
            vTaskDelay(3000);
            break;
          case 8:
            dog->action_run("scrape_a_bow"); //인사(절)
            vTaskDelay(3000);
            break;
          case 9:
            dog->action_run("nodding_motion"); //고개 끄덕이기
            vTaskDelay(3000);
            break;
          case 10:
            dog->action_run("boxing"); //복싱
            vTaskDelay(3000);
            break;
          case 11:
            dog->action_run("stretch_oneself"); //스트레칭
            vTaskDelay(3000);
            break;
          case 12:
            dog->action_run("pee"); //소변보기
            vTaskDelay(3000);
            break;
          case 13:
            dog->action_run("press_up"); //팔굽혀펴기
            vTaskDelay(3000);
            break;
          case 14:
            dog->action_run("rotation_pitch"); //PITCH 회전
            vTaskDelay(3000);
            break;
          case 15:
            dog->action_run("rotation_roll"); //ROLL 회전
            vTaskDelay(3000);
            break;
          case 16:
            dog->action_run("normal_attitude"); //차렷
            vTaskDelay(3000);
            break;
        }
      }else{
        switch(actions){
          // case n:
          //   break;
        }
      }
      actions_flg = 0;
    }else if(homeostasis_flg == 1){ //자동 균형(자세 안정화) 기능
      dog->homeostasis(true);
      while(true){
        if(homeostasis_flg == 0){ //자동 균형 정지
          dog->homeostasis(false);
          vTaskDelay(2000);
          break;
        }else if(!(dog->read_homeostasis_status())){ //MechDog가 넘어진 경우
          mySerial.printf("CMD|%d|%d|%d|$",rec_data[0],rec_data[1],0); //넘어짐 피드백
          homeostasis_flg = 0;
          break;
        }
        vTaskDelay(10);
      }
    }
    vTaskDelay(10);
  }
}
