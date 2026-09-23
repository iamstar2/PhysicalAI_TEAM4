# firmware/ — MechDog 본체(ESP32) 펌웨어

각 파트의 **MechDog 본체에 올리는 Arduino 스케치**를 둔다.
PC·라즈베리파이에서 도는 서비스 코드는 여기 없다.

| 폴더 | 파트 | 역할 | 문서 |
|---|---|---|---|
| [`mechdog_b_body/`](mechdog_b_body/) | **B (대화)** | 터치·초음파 센서를 MQTT 로 발행, 눈 LED 색 구독 | [README](mechdog_b_body/README.md) |

**빌드 환경·업로드·`secrets.h` 설정은 각 폴더 README 에 있다.** 여기서는 반복하지 않는다.

---

## 새 파트 펌웨어를 만들 때

`mechdog_b_body/` 를 복사해서 시작하면 **Wi-Fi · MQTT · LWT 골격**을 그대로 쓸 수 있다.
빌드 환경(코어 버전·보드 선택)도 그 README 를 따르면 된다.

다만 **B 에는 이동 코드가 없다** — B 는 걷지 않아서 일부러 뺐다.
이동·동작이 필요하면 아래에서 가져와 붙인다.

```
references/03 Arduino Programming Projects/05 Serial .../MechDog_uart/
  move(보폭_mm, 회전각_도)   보폭 0 이면 제자리 회전
  action_run(그룹명)         동작 그룹 16종
```

---

## 서보 과열 — 안 쓰는 서보를 세워두지 말 것

벤더 예제는 전부 `MechDog_init()` 을 먼저 부르는데, **이게 서보 8개를 기본 자세로 세우고
그 자세를 계속 유지시킨다.** 4족 로봇이 서 있으려면 서보가 쉬지 않고 토크를 내야 하고,
그 전류가 그대로 열이 된다 — 실제로 **한 시간 만에 다리 모터가 만지기 뜨거울 정도로
과열**된 적이 있다 (`09_작업기록 LOG-30`).

**센서만 읽는 용도면 부르지 않아도 된다.** `Ultrasound_init()` 이 I2C 버스를 스스로 켜므로
초음파·터치는 정상 동작한다. B 펌웨어가 그렇게 돼 있다.

반대로 **자세 제어(2 legs stand 등)가 필요하면 반드시 불러야 한다.**
이때 저전압 "삐" 알람이 거슬리면 한 줄로 끌 수 있다.

```cpp
mechdog.MechDog_init();
mechdog.disableLowPowerAlarm();   // 저전압 경보만 끈다
```

`disableLowPowerAlarm()` 은 내부적으로 `bt_open = false` 한 줄이라
**경고음(`playTone`)은 그대로 살아 있다.** `MechDog_init()` 을 빼거나 부저 태스크를 지우면
경고음도 같이 죽으니 그렇게 하지 말 것.

---

## 접속 정보는 커밋하지 않는다

```
secrets.example.h   ← 저장소에 있음. 복사해서 쓴다
secrets.h           ← .gitignore
```

> **브로커 IP 가 펌웨어에 박힌다.** 공유기가 다른 IP 를 주면 본체가 조용히 죽고
> 에러도 안 난다 — `online:false` 만 남아서 "꺼져 있음"과 구분이 안 된다 (`LOG-60`).
> 시연 전에 **브로커 기계 IP 를 고정**하고, 바뀌었으면 **미리** 재업로드할 것.
