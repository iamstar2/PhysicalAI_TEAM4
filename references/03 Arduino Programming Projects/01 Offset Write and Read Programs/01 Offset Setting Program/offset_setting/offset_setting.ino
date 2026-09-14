#include "mech_base_types.h"
#include "HW_MechDog.h"

/*
   Arduino 프로그램을 다운로드하면 ESP32의 MicroPython 펌웨어가 지워지면서 기존에 설정된 서보모터 오프셋도 함께 삭제됩니다.
   따라서 프로그램을 다운로드하기 전에 먼저 상위 컴퓨터(호스트 소프트웨어)에서 현재 서보모터 오프셋 값을 확인하고 기록한 뒤, 그 값을 오프셋 배열에 입력해야 합니다.
   오프셋 설정 프로그램은 MechDog에서 한 번만 실행하면 되며, 그 값은 MechDog의 Arduino 프로그래밍 환경 내에 저장됩니다.
*/

//오프셋 배열: 0번째 값은 방향 오프셋(0보다 크면 좌측으로 치우침, 0보다 작으면 우측으로 치우침)이고, 1~8번째 값은 PWM 서보모터 1~8번의 오프셋입니다.
int8_t MechDog_offset[9] = {-3, -11, -24, -31, -2, -21, 30, -23, 15};
//오프셋 읽기 배열: 읽어온 오프셋 값을 저장하는 데 사용합니다.
int8_t result_offset[9];
int8_t step = 0;

MechDog mechdog;

void setup() {
  Serial.begin(115200);
  mechdog.MechDog_init();  //MechDog 초기화
  delay(1000);
}

void loop() {
  userTask();
}

void userTask(){
  switch(step){
    case 0:
      mechdog.setsave_all_offset(MechDog_offset); //MechDog의 오프셋을 설정하고 저장합니다.
      delay(500);
      step++;
      break;
    case 1:
      mechdog.read_all_offset(result_offset); //MechDog에 저장된 오프셋을 읽어와 result_offset에 저장합니다.
      Serial.print("{");
      for (int i = 0; i<9; i++) {
        Serial.print(result_offset[i]);
        if(i<8) Serial.print(",");
      }
      Serial.println("}");
      break;
  }
  delay(1000);
}
