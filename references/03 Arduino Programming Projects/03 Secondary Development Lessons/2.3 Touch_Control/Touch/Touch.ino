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

  btn.Button_init(2); //버튼 초기화, 매개변수 2는 터치 센서 기능을 나타냄
  btn.Clicked(on_button1_clicked);
  delay(1000);
}

void loop() {
  userTask();
}

/* 사용자 함수 */
void userTask(){
  if(enter_flag == 1){
    switch (step) {
      case 0:
        //기본 동작 그룹 실행: 앉기
        mechdog.action_run("sit_dowm");
        delay(1500);
        step++;
        break;
      case 1:
        //기본 동작 그룹 실행: 엎드리기
        mechdog.action_run("go_prone");
        delay(1500);
        step++;
        break;
      case 2:
        //기본 동작 그룹 실행: 서기
        mechdog.action_run("stand_four_legs");
        delay(1500);
        step = 0;
        break;
    }
    enter_flag = 0;
  }
  delay(100);
}

/* 버튼 콜백 함수 */
void on_button1_clicked(){
  enter_flag = 1;
}