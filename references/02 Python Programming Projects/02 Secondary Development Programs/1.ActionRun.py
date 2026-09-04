import Hiwonder
import time
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()

# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(2)

# 메인 함수
def main():
  global mechdog

  mechdog.action_run("left_foot_kick")
  time.sleep(3)

# 메인 함수 실행
main()
