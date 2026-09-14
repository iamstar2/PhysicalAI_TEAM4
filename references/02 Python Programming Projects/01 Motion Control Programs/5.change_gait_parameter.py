import Hiwonder
import time
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()


# 메인 함수
def main():
  # MechDog 초기 자세 설정
  mechdog.set_default_pose()
  # 지연 함수, 매개변수는 지연 시간(단위: 초)
  time.sleep(2)
  # 보행(걸음걸이) 파라미터 설정, 매개변수 내용은 다음과 같음:
  # 매개변수1: 발끝이 지면에서 떨어져 있는 시간;
  # 매개변수2: 발끝이 지면에 닿아 있는 시간;
  # 매개변수3: 다리를 들어 올리는 높이.
  mechdog.set_gait_params(150,500,40)
  mechdog.move(50,0)
  time.sleep(5)
  mechdog.move(0,0)
  time.sleep(3)
  mechdog.set_gait_params(100,300,20)
  mechdog.move(50,0)
  time.sleep(5)
  mechdog.move(0,0)
  time.sleep(3)

# 메인 함수 실행
main()
