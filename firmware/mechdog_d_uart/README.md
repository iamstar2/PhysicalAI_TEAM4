# mechdog_d_uart 펌웨어 패치 제안 (미적용 · 미업로드)

이 폴더는 **`references/`의 원본 Hiwonder 공식 예제를 절대 수정하지 않기 위해** 분리한
패치 제안 공간이다. `references/03 Arduino Programming Projects/05 Serial Communication
Practical Lessons/MechDog_Slave_Program/MechDog_uart/` 원본은 그대로 두고, 여기에만
변경안을 둔다.

## 현재 상태: 제안 단계, 실물에 적용된 적 없음

- ESP32에 업로드한 적 없음.
- 실물 명령을 보낸 적 없음(테스트는 전부 `security-dashboard/tests/`의 Mock/Fake로만 진행).
- 아래 "적용 전 필수 확인"을 팀이 확인하기 전까지 업로드하지 않는다.

## 대상 파일과 변경 내용

대상: `references/03 Arduino Programming Projects/05 Serial Communication Practical
Lessons/MechDog_Slave_Program/MechDog_uart/MechDog_uart.ino`

`switch(rec_data[0])`의 기존 `case 6`(배터리 잔량, 169-173행) 바로 뒤에 `case 7`
하나만 추가한다. 다른 파일(`HW_MechDog.*`, `Hiwonder.*` 등)은 건드리지 않는다 -
`MechDog` 클래스가 이미 `PowerBuzzer`를 public 상속하고 있어(`HW_MechDog.h:28`)
`mechdog.playTone(...)`을 이 파일 안에서 바로 호출할 수 있기 때문이다
(`Hiwonder.cpp:148` `void PowerBuzzer::playTone(int duty, int btime, bool state)`).

패치 내용은 `0001-add-buzzer-case7.patch`(unified diff, `references/` 원본 대비)에
있다. 적용 예시(팀이 실제로 적용하기로 결정했을 때):

```bash
git apply firmware/mechdog_d_uart/0001-add-buzzer-case7.patch
```

## 새 명령 형식

- 부저 1회 트리거(200ms, 논블로킹): `"CMD|7|1|$"`
- 별도 "끄기" 명령은 만들지 않았다 - 펌웨어가 200ms 뒤 자동으로 꺼지므로(`Buzzer_Task`의
  `userTone` 원샷 동작, `Hiwonder.cpp:119-146` 참고), PC 쪽에서 반복 전송을 멈추면
  그걸로 충분하다고 판단했다(`security-dashboard/app/robot_commands.py`의
  `_buzzer_loop`가 반복 전송을 담당).

## duty=500 값의 근거

임의로 정한 값이 아니라, 같은 파일의 저전압 경보 로직(`Hiwonder.cpp:129`
`ledcWrite(self->Buzzer_channel, 500)`)에서 실제로 소리가 나는 것으로 보이는 값을
그대로 재사용했다. **다만 경보음으로서 크기/음색이 적절한지는 실물에서 들어봐야
확정된다** - 추측하지 않는다.

## 적용 전 필수 확인 (팀 확인 사항)

1. **백업**: 업로드 전에 현재 로봇에 올라가 있는 펌웨어를 `esptool.py read_flash`로
   통째로 백업할 것(일반 ESP32 절차 - MechDog 저장소에 전용 절차는 없음).
2. **핀 배선 확인**: 이 프로토콜은 `HardwareSerial mySerial(1)`로 GPIO32(RX)/33(TX)를
   쓴다(`MechDog_uart.ino:3-4,17`) - 동봉 USB 케이블이 연결되는 UART0(플래싱용)과
   다른 물리 핀일 가능성이 높다. 실제로 GPIO32/33이 어떤 커넥터로 나와 있는지 실물을
   보고 확인해야 한다.
3. **현재 로봇에 올라간 펌웨어가 이 참고 예제와 동일한지 확인**: 출고 펌웨어가 GitHub
   공개 예제와 정확히 같다는 보장이 없으므로, 이 패치를 그대로 적용하기 전에 실제
   설치된 소스와 비교할 것.

이 세 가지가 확인되기 전까지는 패치를 만들기만 하고 적용/업로드하지 않는다.
