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
  mechdog.move(50,-16)
  time.sleep(5)
  mechdog.transform([0, 0, 1 * 20], [0, 0, 0], 1000)
  time.sleep(5)
  mechdog.transform([0, 0, -1 * 30], [0, 0, 0], 1000)
  time.sleep(5)
  mechdog.move(0,0)
  time.sleep(2)
  # MechDog 초기 자세 설정
  mechdog.set_default_pose()

# 메인 함수 실행
main()

