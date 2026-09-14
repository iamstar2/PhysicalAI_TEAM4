import Hiwonder
import time
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()
# 버튼 눌림 플래그
enter_flag = 0
# 동작 그룹 번호
action_num = 0
# 버튼 객체 생성
button2 = Hiwonder.Button(2)


# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(1)

# 메인 함수
def main():
  global enter_flag
  global action_num

  while True:
    # 버튼이 눌렸다면
    if (enter_flag==1):
      if (action_num==1):
        # 기본 동작 그룹 실행: 앉기
        mechdog.action_run("sit_dowm")
        time.sleep(1.5)
        action_num+=1
      elif (action_num==2):
        # 기본 동작 그룹 실행: 엎드리기
        mechdog.action_run("go_prone")
        time.sleep(1.5)
        action_num+=1
      else:
        # 기본 동작 그룹 실행: 서기
        mechdog.action_run("stand_four_legs")
        time.sleep(1.5)
        action_num = 1
      # 눌림 플래그 초기화
      enter_flag = 0
    else:
      time.sleep(0.2)

# 버튼 짧게 눌렀을 때 호출되는 함수
def on_extbutton_clicked():
  global enter_flag
  enter_flag = 1


# 버튼 짧게 눌렀을 때 호출할 함수 등록
button2.Clicked(on_extbutton_clicked)

# 메인 함수 실행
main()
