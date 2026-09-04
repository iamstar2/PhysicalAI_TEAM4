import Hiwonder
import time
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()

# 메인 함수
def main():
  # 지연 함수, 매개변수는 지연 시간(단위: 초)
  time.sleep(2)
  # move() 함수
  # 매개변수1: 보폭(단위 mm)(양수는 전진, 음수는 후진);
  # 매개변수2: 회전 각도(단위: 도), 양수는 좌회전, 음수는 우회전
  mechdog.move(50,20) # 좌회전
  time.sleep(10)
  mechdog.move(0,0)
  time.sleep(2)
  mechdog.move(50,-20) # 우회전
  time.sleep(5)
  # 정지
  mechdog.move(0,0)
  time.sleep(2)

# 메인 함수 실행
main()

