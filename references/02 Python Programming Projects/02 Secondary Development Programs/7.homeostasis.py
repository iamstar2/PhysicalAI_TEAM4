import Hiwonder
import time
import Hiwonder_IIC
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()

# 발광 초음파 센서 객체 초기화
i2c1 = Hiwonder_IIC.IIC(1)
i2csonar = Hiwonder_IIC.I2CSonar(i2c1)
# 부저 객체 생성
beep = Hiwonder.Buzzer()

# MechDog 초기 자세 설정
mechdog.set_default_pose()
time.sleep(1)


# 메인 함수
def main():
  # 발광 초음파 색상 설정 함수
  # 매개변수1: 설정할 램프, 0은 두 램프 모두 설정, 1은 램프1 설정, 2는 램프2 설정;
  # 매개변수2, 3, 4: 각각 빨강, 초록, 파랑 3가지 색상 값에 해당
  i2csonar.setRGB(0,0xff,0xcc,0x33)
  # 자동 균형(자세 안정화) 상태 켜기
  mechdog.homeostasis(True)
  time.sleep(2)
  # 자동 균형 상태인지 확인하고, 자동 균형 상태를 벗어나면 이 루프를 종료한다
  while mechdog.read_homeostasis_status():
    time.sleep(0.1)
  i2csonar.setRGB(0,0x33,0x33,0xff)
  beep.playTone(800,100,True)

# 메인 함수 실행
main()

