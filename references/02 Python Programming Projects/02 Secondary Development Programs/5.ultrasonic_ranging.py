import Hiwonder
import time
import Hiwonder_IIC
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()
# 도트 매트릭스 디스플레이 객체 생성
tm = Hiwonder.Digitaltube()
# IIC1 객체 생성
i2c1 = Hiwonder_IIC.IIC(1)
# 발광 초음파 센서 객체 생성
i2csonar = Hiwonder_IIC.I2CSonar(i2c1)

# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 디스플레이 밝기를 4로 설정
tm.setBrightness(4)
# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)

# 초음파로 측정한 거리
distance = 0

# 메인 함수
def main():
  global distance

  while True:
    distance = i2csonar.getDistance()
    tm.showNum(distance)
    if (distance<15):
      # 발광 초음파 색상 설정 함수
      # 매개변수1: 설정할 램프, 0은 두 램프 모두 설정, 1은 램프1 설정, 2는 램프2 설정;
      # 매개변수2, 3, 4: 각각 빨강, 초록, 파랑 3가지 색상 값에 해당
      i2csonar.setRGB(0,0xff,0x00,0x00) # 빨간색으로 설정
    else:
      if (distance>40):
        i2csonar.setRGB(0,0x00,0x00,0x99) # 파란색으로 설정
      else:
        i2csonar.setRGB(0,0xfd,0xd0,0x00) # 노란색으로 설정
    time.sleep(0.1)

# 메인 함수 실행
main()
