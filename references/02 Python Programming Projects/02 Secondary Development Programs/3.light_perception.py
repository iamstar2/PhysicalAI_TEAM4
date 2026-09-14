import Hiwonder
import time
from HW_MechDog import MechDog

# 조도 센서 객체 생성
adc = Hiwonder.LightSensor()
# MechDog 객체 초기화
mechdog = MechDog()

# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)
# 조도 임계값
Intensity_threshold = 100
# 읽어들인 밝기 값
brightness = 0

# 메인 함수
def main():
  global Intensity_threshold
  global brightness

  while True:
    # 조도 값 읽기
    brightness = adc.read()
    # 밝기 값이 임계값보다 크면
    if (brightness>=Intensity_threshold):
      # 서기 동작 실행
      mechdog.action_run("stand_four_legs")
      time.sleep(2)
      # 걷기
      mechdog.move(80,0)
      time.sleep(1)
      # 밝기 값이 임계값보다 큰 동안 계속 대기하고, 임계값보다 작아지면 루프를 벗어난다.
      while adc.read()>Intensity_threshold:
        time.sleep(0.1)
    else:
      # 정지
      mechdog.move(0,0)
      time.sleep(2)
      # 엎드리기 동작 그룹 실행
      mechdog.action_run("go_prone")
      time.sleep(2)
      # 밝기 값이 임계값보다 작은 동안 계속 대기하고, 임계값보다 커지면 루프를 벗어난다.
      while adc.read()<Intensity_threshold:
        time.sleep(0.1)

# 메인 함수 실행
main()
