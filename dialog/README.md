# MechDog B — 음성 대화 유닛

> 담당: 김별이 · 게이트에서 **방문자에게 목적지를 물어 확정하고 C(에스코트)에게 넘기는** 파트.

방문자가 로봇 등을 터치하고 말하면, 목적지 7곳 중 하나로 확정해서 `dialog.result` 를 발행한다.
**오디오는 RPi5 밖으로 나가지 않는다** (`CON-B-03`) — MQTT 로 나가는 건 텍스트뿐이다.

---

## 1. 한 번에 보는 흐름

```
A(게이트)  ──gate.session──▶  B

  인사 "제 등을 터치하고 말씀해 주세요"
    ↓ 터치 (본체 ESP32 → MQTT)
  녹음 → 엔드포인팅(700ms 무음) → STT(whisper.cpp base)
    ↓
  LLM 분류기 ──실패시──▶ 룰 매칭
    ↓
  "입고 도크 맞으실까요?"  ──아니요──▶ 재질문(최대 2회) ──▶ D 에스컬레이션
    ↓ 네
  "입고 도크는 오른쪽 통로 끝이에요. 직접 안내해 드릴까요?"
    ├ 네    ──▶  dialog.result 발행  ──▶  C(에스코트)
    └ 괜찮아요 ──▶  발행 안 함 · 인사하고 터치 대기로 복귀
```

**에스코트는 기본이 아니다.** 많은 방문자는 위치만 알면 혼자 간다. 수락해야만 C 를 부른다.

---

## 2. 팀 인터페이스 (이것만 알면 된다)

| 방향 | 토픽 | 언제 |
|---|---|---|
| **수신** | `mechdog/v1/gate/session` | A 가 인가·PPE 판정을 마치고 넘길 때 |
| **발행** | `mechdog/v1/dialog/result` | 목적지 확정 **AND 에스코트 수락** 시 |
| **발행** | `mechdog/v1/alert/event` | 이탈(`dialog_timeout`) · 실패(`dialog_failed`) |
| 내부 | `mechdog/internal/b/{touch,ultrasonic,eye,status}` | 본체 ESP32 와만 주고받음 — **공용 스키마 밖** |

> `dialog.result` 는 **에스코트를 수락했을 때만** 나간다. 방문자가 "괜찮습니다" 하면
> 아무것도 발행하지 않는다 — C 가 움직일 이유가 없고, 거절은 이상 상황이 아니다.
>
> 내부 토픽을 `mechdog/v1/#` 에 넣지 않은 이유: 공용 스키마가 `additionalProperties:false` 라
> 정의되지 않은 메시지를 끼워 넣으면 **다른 노드의 검증이 깨진다**.

---

## 3. 파일 지도

| 파일 | 하는 일 |
|---|---|
| **`session.py`** | 대화 전체 흐름 (`04_B_비즈니스_Flow.md` 의 ①~㉛) |
| `audio.py` | 녹음(VAD 엔드포인팅) · 재생. 장치를 **이름으로** 찾는다 |
| `stt.py` | `whisper.cpp` 호출 래퍼 |
| `llm_fallback.py` | **LLM 분류기** — 목적지 / 말로만 알려주는 곳 / 일정 매칭 / 확인 응답 |
| `matcher.py` | 룰 매칭 + 신뢰도 산정 (LLM 실패 시 폴백, **모호 판정 전담**) |
| `hangul.py` | 자모 분해 · 편집거리 |
| `destinations.py` | 목적지 사전(키워드) + STT 도메인 프롬프트 |
| `info_places.py` | 데려다주지 않고 **말로만 알려주는 곳** (화장실·계단 …) |
| `bus.py` | MQTT 송수신 |
| `eye.py` | 눈 LED 상태 발행 |
| `gen_tts.py` | 안내 음성 생성기 (Gemini TTS → wav 캐시) |
| **`phrases.json`** | **모든 멘트.** 문구를 고칠 때 보는 파일은 이것 하나 |
| `schedule.json` | 시연용 방문 일정 (LLM 이 "두 시 반에 오라고 해서요" 를 풀 때 씀) |
| `testset.json` | 실사람 음성 테스트셋 59문장 (대본 + 기대값) |

| `vol_daemon.py` | USB 스피커 볼륨 놉 → ALSA 연결 (**RPi5 에서 crontab `@reboot` 로 상주**) |

관련 코드가 더 있다: `firmware/mechdog_b_body/` (본체 센서·눈 LED),
`tools/gen_*_flowchart.py` (도면 생성기).

---

## 3-1. 이 폴더는 **RPi5 에서 돈다** — 서버 PC 용이 아니다

> `docker-compose.host2.yml` 에 `dialog-service` 항목이 남아 있지만 **쓰지 않는다.**
> 09-17 회의에서 공용 GPU 서버 계획을 접고 **각자 로컬 실행**으로 바꾸면서,
> B 는 RPi5 단독으로 도는 것으로 정해졌다. compose 파일 정리는 아직 안 됐다.

### 다른 기계로 옮길 수 있나 — 있다

장치·경로·모델이 전부 환경변수로 빠져 있어서 **코드를 안 고치고 옮길 수 있다.**

```
MIC_DEV · SPK_DEV · MIC_NAME · SPK_NAME      오디오 장치
WHISPER_BIN · WHISPER_MODEL · WHISPER_THREADS  STT 엔진
MQTT_HOST · MQTT_PORT                         브로커
TTS_ENGINE · GEMINI_MODEL                     TTS
```

**딱 하나 걸리는 게 오디오다.** `audio.py` 가 ALSA 의 `arecord`/`aplay` 를 직접 부른다.

| 옮길 곳 | 할 일 |
|---|---|
| **리눅스 PC** | 그대로 된다. `alsa-utils` 설치하고 `MIC_DEV`/`SPK_DEV` 만 맞추면 끝 |
| **Docker (리눅스)** | 컨테이너에 사운드 장치를 통과시켜야 한다 — `devices: - /dev/snd` |
| **Windows** | `arecord`/`aplay` 가 없다. **`audio.py` 만 다시 써야** 한다 (sounddevice 등) |

### "서버 연산"으로 바꾸려면 — `stt.py` 한 파일

옮기는 방식이 둘인데 난이도가 다르다.

**① 통째로 서버에서 실행** — 마이크·스피커를 서버 PC 에 꽂는다.
바꿀 코드는 없다(리눅스 기준). 다만 **마이크가 게이트에 있어야 하는데 선이 닿아야 한다.**

**② RPi5 는 입출력만, 연산만 서버로** — 09-12 에 논의됐던 안.
`stt.py` 가 지금은 로컬 `whisper-cli` 를 `subprocess` 로 부르는데,
이걸 **wav 를 서버로 POST → 텍스트 수신** 으로 바꾸고 서버에 whisper HTTP 래퍼를 세운다.
**고칠 파일은 `stt.py` 하나다.**

②는 실측해 둔 근거가 있다 (`09_작업기록 LOG-33`).

| | 속도 | 정확도 |
|---|---|---|
| 파이 로컬 `tiny` | 909 ms | 2/12 |
| **파이 → PC `base`** | **637 ms** | **8/12** |

전송 오버헤드(약 81 ms)를 포함해도 PC 쪽이 **1.4배 빠르고 정확도 4배**였다.
다만 이건 데스크톱(i5-12600KF) 기준이고, **팀 노트북은 외장 그래픽이 없어**(09-17 확인)
그만큼 안 나올 수 있다. 지금은 RPi5 단독으로 가고, 지연이 문제되면 ②를 검토한다.

---

## 4. 돌려보기

전부 **RPi5(파이)** 에서 돈다. 파이썬은 반드시 `~/venv_stt/bin/python` 을 쓴다
(시스템 python3 에는 `paho`·`numpy` 가 없다).

```bash
ssh mechdog@172.30.1.65                 # mDNS(mechdog-b.local)가 가끔 안 풀린다
set -a; . ~/.gemini_env; set +a         # Gemini API 키 (저장소에 없다)
cd ~/dialog

# 실제 대화 한 판 (본체·브로커 필요)
MQTT_HOST=<PC IP> WHISPER_MODEL=$HOME/whisper.cpp/models/ggml-base.bin \
  ~/venv_stt/bin/python -u session.py --demo

# 흐름 검증 — 사람 없이 (녹음 파일 주입 · 무음)
MQTT_HOST=127.0.0.1 SPK_DEV=null \
  WHISPER_MODEL=$HOME/whisper.cpp/models/ggml-base.bin \
  ~/venv_stt/bin/python -u ~/session_sim.py

# 정확도 측정 — 실사람 59문장
~/venv_stt/bin/python -u ~/score.py

# 멘트를 고쳤으면 음성 다시 만들기 (약 4분)
rm -f ~/tts_cache/*.wav
TTS_ENGINE=gemini TTS_GAP_S=4 ~/venv_stt/bin/python gen_tts.py
```

`SPK_DEV=null` 은 **소리 없이** 재생 경로를 그대로 탄다. 밤에 돌릴 때 쓴다.

---

## 5. 지금 성능 (실측)

| | |
|---|---|
| 목적지 해결률 | **88 %** (52/59, 실사람 음성) |
| 흐름 시나리오 | **7/7** |
| 응답 지연 | 약 **3,860 ms** / 상한 4,000 ms (`NFR-B-101`) |

지연 분해: 엔드포인팅 700 + STT 1,900 + LLM 1,000 + 매칭 20 + 판정 10 + 재생 50 + 스피커 152

> **여유가 140 ms 뿐이다.** STT 나 LLM 모델을 키우면 바로 넘친다.

---

## 6. 설계에서 알아둘 것 세 가지

**① LLM 이 먼저고 룰이 폴백이다.**
원래는 반대였는데, 짧은 키워드가 엉뚱한 음절을 잡는 사고가 **네 번** 반복됐다
(`들어왔`→`들었`, `네`→`내`, `퇴장`→`터장`, `나가`→`라가`). 고칠 때마다 다른 곳이 터져서
판단 주체를 바꿨다. 룰은 **인터넷이 끊겼을 때**와 **모호 판정**(LLM 은 애매하면 null 을 낸다)
때문에 남는다.

**② LLM 은 문장을 만들지 않는다.**
목적지 key 하나만 돌려주고, 방문자가 듣는 말은 전부 **미리 합성해 둔 고정 멘트**다.
환각이 구조적으로 불가능하다. 런타임 TTS 는 실측 3.0~6.7초로 예산을 혼자 넘어서 쓰지 않는다.

**③ 확인 질의가 마지막 안전장치다.**
어떤 경로로 목적지가 정해졌든 **반드시 되묻는다**(`BR-B-10`).
잘못 확정하는 쪽이 못 확정하는 쪽보다 위험하다 — 반대편 도크로 안내하면 방문자가
창고를 가로질러 헛걸음한다.

---

## 7. 아직 안 된 것

- **`음성안내` 문구가 비어 있다** — 화장실·계단은 **시연장 배치가 정해져야** 쓸 수 있다.
  비어 있으면 인식 자체를 안 한다(틀린 위치를 말하는 것보다 낫다)
- **목적지 위치 설명이 임시값이다** — 상상해서 넣었고, 실제 배치로 교체해야 한다
- **소음 환경 녹음 미실시** · **화자 1명** (원래 계획은 4명)
- 눈 LED 색상 실물 확인, 음성 명령(앉아·손) — `09_작업기록.md` 참고

---

## 8. 더 볼 것

| 문서 | 내용 |
|---|---|
| `work_docs/04_B_비즈니스_Flow.md` | 업무 흐름 ①~㉛ · **실제 발화 59문장이 어느 경로를 타는지**(§2.1-E) |
| `work_docs/05_B_AI_Flow.md` | 모델 선정 근거 · 파이프라인 · 테스트셋 |
| `work_docs/03_B_비기능요구사항_정의서.md` | 지연 예산 |
| **`work_docs/09_작업기록.md`** | **왜 이렇게 됐는지** — 판단과 시행착오 56건. 코드를 고치기 전에 여기부터 본다 |
| `work_docs/exports/*.drawio` | 도면 (원본은 `tools/gen_*_flowchart.py`) |
