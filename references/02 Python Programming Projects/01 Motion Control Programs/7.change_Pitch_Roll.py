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
  # 자세 변환 함수
  # 매개변수1: 몸체 평행 이동(x, y, z축)
  # 매개변수2: 몸체 회전(x, y, z축을 기준으로 회전)
  # 매개변수3: 변환에 걸리는 시간
  mechdog.transform([0, 0, 0], [1 * 15, 0, 0], 500) # x축을 기준으로 회전(즉, Pitch)
  time.sleep(2)
  mechdog.transform([0, 0, 0], [-1 * 30, 0, 0], 1000)
  time.sleep(2)
  # MechDog 초기 자세 설정
  mechdog.set_default_pose()
  time.sleep(2)
  mechdog.transform([0, 0, 0], [0, 1 * 15, 0], 500) # y축을 기준으로 회전(즉, Roll)
  time.sleep(2)
  mechdog.transform([0, 0, 0], [0, -1 * 30, 0], 1000)
  time.sleep(2)
  # MechDog 초기 자세 설정
  mechdog.set_default_pose()
  time.sleep(2)

# 메인 함수 실행
main()
