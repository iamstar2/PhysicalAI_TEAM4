#include "mech_base_types.h"
#include "HW_MechDog.h"

int8_t step = 0;

int8_t enter_flag = 0;
int8_t speed = 40;

MechDog mechdog;
Button btn;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init(); //MechDog 초기화

  btn.Button_init(1); //버튼 초기화, 매개변수 1은 버튼 기능을 나타냄
  btn.Clicked(on_button1_clicked);
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  /*
     move() 함수
     매개변수1: 보폭(단위 mm)(양수는 전진, 음수는 후진);
     매개변수2: 회전 각도(단위: 도), 양수는 좌회전, 음수는 우회전
  */
  if(enter_flag == 1){
    switch (step) {
      case 0:
        mechdog.move(speed,0);
        delay(5000);
        speed += 20;
        step++;
        break;
      case 1:
        mechdog.move(speed,0);
        delay(5000);
        speed += 20;
        step++;
        break;
      case 2:
        mechdog.move(speed,0);
        delay(5000);
        speed += 20;
        step++;
        break;
      case 3:
        mechdog.move(speed,0);
        delay(5000);
        speed = 40;
        step = 0;
        break;
    }
    mechdog.move(0,0);
    enter_flag = 0;
  }
  delay(100);
}

/* 버튼 콜백 함수 */
void on_button1_clicked(){
  enter_flag = 1;
}