import Hiwonder
import time
import Hiwonder_IIC
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()
# IIC1 객체 생성
i2c1 = Hiwonder_IIC.IIC(1)
# 발광 초음파 센서 객체 생성
i2csonar = Hiwonder_IIC.I2CSonar(i2c1)
# 부저 객체 생성
beep = Hiwonder.Buzzer()

# 초음파로 측정한 거리
distance = 0

# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)


# 메인 함수
def main():
  global distance

  while True:
    # 발광 초음파가 측정한 거리를 가져옴
    distance = i2csonar.getDistance()
    # 거리가 10cm보다 작으면
    if (distance<10):
      # 발광 초음파 색상 설정 함수
      # 매개변수1: 설정할 램프, 0은 두 램프 모두 설정, 1은 램프1 설정, 2는 램프2 설정;
      # 매개변수2, 3, 4: 각각 빨강, 초록, 파랑 3가지 색상 값에 해당
      i2csonar.setRGB(0,255,0,0) # 빨간색으로 설정
    else:
      if (distance>50):
        i2csonar.setRGB(0,0,255,0) # 초록색으로 설정
      else:
        i2csonar.setRGB(0,(250-((round(distance))*5)),((round(distance))*5),0) # 거리에 따라 빨강, 초록 2가지 색상을 설정
    time.sleep(0.1)

# 부저 울림 함수
def start_main1():
  global distance

  while True:
    # 거리가 50cm보다 작을 때, 거리에 따라 울림
    if (distance<=50):
      beep.playTone(800,100,True)
      time.sleep((distance/50))
    else:
      time.sleep(50)

# 부저 울림 스레드 등록
Hiwonder.startMain(start_main1)
# 메인 함수 실행
main()
