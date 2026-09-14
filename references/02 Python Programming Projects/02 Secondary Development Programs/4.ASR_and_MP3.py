import Hiwonder
import time
import Hiwonder_IIC
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()
# IIC2 객체 생성
i2c2 = Hiwonder_IIC.IIC(2)
# 음성 인식 모듈 객체 생성
myasr = Hiwonder_IIC.ASR(i2c2)
# IIC1 객체 생성
i2c1 = Hiwonder_IIC.IIC(1)
# MP3 모듈 객체 생성
mp3 = Hiwonder_IIC.MP3(i2c1)
# 인식 결과
recognize_result = 0


# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 반복 인식 모드로 설정
myasr.setMode(1)
# MP3 음량을 30으로 설정
mp3.volume(30)

# 음성 인식 단어(명령어) 등록, 한 번만 설정하면 되며 이후에는 False로 바꿔도 됨
if True:
  myasr.addWord(0,"ni hao")
  myasr.addWord(1,"xiang qian")
  myasr.addWord(2,"xiang hou")
  myasr.addWord(3,"zuo zhuan")
  myasr.addWord(4,"you zhuan")
  myasr.addWord(5,"ting zhi")

# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)


# 메인 함수
def main():
  global recognize_result

  while True:
    # 인식 결과를 가져옴, 결과가 없으면 0을 반환
    recognize_result = myasr.getResult()
    # 전진 인식됨
    if (recognize_result==1):
      mp3.play(1)
      mp3.play()
      mechdog.move(80,0)
      time.sleep(3)
      mechdog.move(0,0)
      time.sleep(2)
    # 후진 인식됨
    if (recognize_result==2):
      mp3.play(2)
      mp3.play()
      mechdog.move(-80,0)
      time.sleep(3)
      mechdog.move(0,0)
      time.sleep(2)
    # 좌회전 인식됨
    if (recognize_result==3):
      mp3.play(3)
      mp3.play()
      mechdog.move(80,30)
      time.sleep(3)
      mechdog.move(0,0)
      time.sleep(2)
    # 우회전 인식됨
    if (recognize_result==4):
      mp3.play(4)
      mp3.play()
      mechdog.move(80,-30)
      time.sleep(3)
      mechdog.move(0,0)
      time.sleep(2)
    time.sleep(0.05)

# 메인 함수 실행
main()


