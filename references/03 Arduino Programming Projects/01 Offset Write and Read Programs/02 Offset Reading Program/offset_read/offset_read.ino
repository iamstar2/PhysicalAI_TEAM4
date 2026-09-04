#include "mech_base_types.h"
#include "HW_MechDog.h"

//오프셋 읽기 배열: 읽어온 오프셋 값을 저장하는 데 사용합니다.
int8_t result_offset[9];

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
  mechdog.read_all_offset(result_offset); //MechDog에 저장된 오프셋을 읽어와 result_offset에 저장합니다.
  Serial.print("{");
  for (int i = 0; i<9; i++) {
    Serial.print(result_offset[i]);
    if(i<8) Serial.print(",");
  }
  Serial.println("}");
  delay(1000);
}
