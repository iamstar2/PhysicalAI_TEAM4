import Hiwonder
import time
from HW_MechDog import MechDog

# MechDog 객체 초기화
mechdog = MechDog()


# MechDog 초기 자세 설정
mechdog.set_default_pose()
# 지연 함수, 매개변수는 지연 시간(단위: 초)
time.sleep(2)
# 보폭을 아주 작게(1밀리미터) 설정하여 제자리 걷기와 비슷하게 만듦
mechdog.move(1,0)
time.sleep(10)
# 정지
mechdog.move(0,0)
