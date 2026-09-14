import Hiwonder
import time
from HW_MechDog import MechDog

# 버튼 눌림 플래그
enter_flag = 0
# 속도 초기값
speed = 40

# MechDog 객체 초기화
mechdog = MechDog()
# 버튼 객체
button1 = Hiwonder.Button(1)

# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)


# 메인 함수
def main():
  global enter_flag
  while True:
    if (enter_flag==1):
      if (speed==40):
        mechdog.move(speed,0)
        time.sleep(10)
        speed = 60
      elif (speed==60):
        mechdog.move(speed,0)
        time.sleep(10)
        speed = 80
      else:
        mechdog.move(speed,0)
        time.sleep(10)
        speed = 40
      # 정지
      mechdog.move(0,0)
      enter_flag = 0

    time.sleep(0.05)

# 버튼 짧게 눌렀을 때 호출되는 함수
def on_button1_clicked():
  global enter_flag
  enter_flag = 1

# 버튼 짧게 눌렀을 때 호출할 함수 등록
button1.Clicked(on_button1_clicked)

# 메인 함수 실행
main()

