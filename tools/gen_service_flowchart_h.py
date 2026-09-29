# -*- coding: utf-8 -*-
"""MechDog **전체 서비스 Flow** — A·B·C·D 통합 .drawio 생성 + 자동 검증.

    PYTHONIOENCODING=utf-8 python tools/gen_service_flowchart.py

`gen_b_flowchart.py`(B 내부)·`gen_ai_flowchart.py`(B 파이프라인)와 **보는 높이가 다르다.**
여기서는 각 노드 **안**을 그리지 않는다. 방문자 한 명이 들어와서 나갈 때까지
**AI 가 몇 번 판단하고, 그 판단이 어떤 메시지로 다음 노드에 넘어가는가**만 그린다.
내부 상세는 각 담당자 도면에 있고, 이 도면은 그것들을 잇는 뼈대다.

**판단의 성격을 색으로 가른다** — 어디까지가 확률적이라 틀릴 수 있고 어디부터가
결정적인지가 이 도면의 핵심 정보다. A 의 얼굴 인식이 틀리면 C 가 엉뚱한 사람을
안내하는데, C 는 자기가 틀렸는지 알 방법이 없다.

**출처**
  A  `work_docs/A_Flow.png` (여도훈) — 모델·지연. `policy.decide()` 이후는 미수령
  B  `dialog/` 실제 코드
  C  `work_docs/DogC_Flow_최신.md` (최현수, **09-14**). PPT(09-07)는 구버전이라 쓰지 않는다
  D  `origin/feature/security-dashboard` 실제 코드 (백경률)
"""
import html
import sys

CX_ = lambda k: 150 + 302 * k         # 흐름은 왼→오른쪽   # noqa: E731
CY = CX_                              # (구 호출부 호환)
cx = lambda x, w: x + w / 2           # noqa: E731

# ---- 레인 --------------------------------------------------------------------
# ---- 레인은 **담당자가 아니라 실행 위치(기계)** 로 나눈다 ------------------------
# A 의 추론은 A 로봇이 아니라 **서버 PC** 에서 돌고, 모든 MQTT 는 **브로커**를 지난다.
# 담당자로 나누면 그 둘이 도면에서 사라진다.
NW = 270                       # 본류 노드 폭
SW = 132                       # 참조 데이터 폭
# 방문자를 **서버 PC 오른쪽**에 둔다 — 왼쪽 끝에 두면 '방문 목적 발화 → B 마이크' 선이
# 서버 레인과 브로커를 통째로 가로지른다. 사람은 게이트 앞과 B 앞 둘 다에 선다.
# 서버 PC 한 통 안에 **vision-service · 브로커 · 보안/대시보드 · 수집기 · DB** 가 다 들어간다
# (docker-compose.host1/2). 그래서 이 레인만 세 칸으로 쪼갠다.
# 도화지처럼 배치한다 — **한 세로줄에 여러 그룹을 쌓는다.**
# 레인마다 한 줄씩 쓰면 노드 1개짜리도 기둥 하나를 통째로 먹어서 가로만 늘어난다
# (직전 판: 클라우드 4 % · 경고 로봇 3 % · 본체 0 % 채움).
NW = 270
SW = 132
GX, GW = 40, 320               # ① 게이트 카메라
SX, SW_ = 380, 660             # ② 서버 PC (Docker)
VX, VW = 1080, 310             # ③ 방문자 · 현장
QX, QW = 1420, 310             # ④ 본체 ESP32 / 외부 클라우드 / 경고 로봇 — 한 줄에 셋
RX, RW = 1750, 490             # ⑤ RPi5 / 에스코트 — 한 줄에 둘

# 가로본에서는 이 값이 전부 **띠의 중심 y** 다 (가로 위치는 CX_(k) 가 정한다)
cg  = 170          # 게이트 카메라
cs  = 430          # 서버 PC — vision-service · 보안 판정 (같은 줄, x 가 다르다)
cd2 = cs
sa  = 580          # 서버 PC 참조 데이터
sd  = sa
BKY, BKH = 660, 86 # 브로커 가로 막대
cv  = 990          # 방문자 · 현장
cq  = 1160         # 본체 · 클라우드 · 경고 로봇 (한 띠, x 가 다르다)
ce = ck = cq
cb  = 1360         # RPi5 · 에스코트 본류
sb  = 1520         # 〃 참조 데이터
cc, sc = cb, sb
cw  = cs
ca = cs                        # A 추론은 서버 PC 칸
cd = cd2

# ---- 스타일 ------------------------------------------------------------------
F = "fontSize=11;"
S_TERM = "rounded=1;arcSize=48;whiteSpace=wrap;html=1;strokeWidth=2;" + F
S_PROC = "rounded=0;whiteSpace=wrap;html=1;strokeWidth=1.5;" + F
S_DEC = "rhombus;whiteSpace=wrap;html=1;strokeWidth=1.5;fontSize=10;"
S_IO = ("shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1;size=16;"
        "whiteSpace=wrap;html=1;strokeWidth=1.5;" + F)
S_WAIT = ("shape=process;whiteSpace=wrap;html=1;backgroundOutline=1;size=0.08;"
          "strokeWidth=1.5;" + F)

S_STORE = ("shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=10;whiteSpace=wrap;"
           "html=1;strokeWidth=1.5;fontSize=9;verticalAlign=middle;")
C_STORE = "fillColor=#FFF9EC;strokeColor=#B98B00;fontColor=#5A4000;"

# 참조 데이터로 가는 선은 **점선 + 화살표 없음**이다.
# 노드 사이를 흐르는 메시지가 아니라 "이걸 보고 판단한다" 는 표시라서 방향이 없다.
REF = "dashed=1;dashPattern=4 3;endArrow=none;strokeColor=#B98B00;"

# 판단의 성격 — 이 도면에서 가장 중요한 구분
C_AI = "fillColor=#F3E8FF;strokeColor=#7C3AED;fontColor=#3B0764;strokeWidth=2.5;"
C_RULE = "fillColor=#EEF4FA;strokeColor=#2D6CDF;fontColor=#123863;"
C_PROC = "fillColor=#FFFFFF;strokeColor=#5A6B7D;fontColor=#26384F;"
C_MSG = "fillColor=#DFF3E8;strokeColor=#1E7F4F;fontColor=#10331F;"
C_V = "fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5A3D00;"
C_WARN = "fillColor=#FDEBE8;strokeColor=#B3341C;fontColor=#5C1B10;"
C_UNK = ("fillColor=#F3F4F6;strokeColor=#8FA0B3;fontColor=#5A6B7D;"
         "dashed=1;dashPattern=6 4;")

nodes, order, bg = {}, [], set()


H_STEPS = (56, 76, 96, 116)      # 노드 높이는 이 넷 중 하나만 쓴다


def snap_h(h: float) -> float:
    """가장 가까운 단계로 올린다. 도형 크기가 15종씩 되면 규칙이 없어 보인다."""
    for step in H_STEPS:
        if h <= step:
            return step
    return h


def N(nid, x, y, w, h, label, style, is_bg=False):
    assert nid not in nodes, nid
    if not is_bg and "cylinder" not in style:
        h = snap_h(h)
    nodes[nid] = dict(x=float(x), y=float(y), w=float(w), h=float(h), label=label, style=style)
    order.append(nid)
    if is_bg:
        bg.add(nid)
    return nid


def P(nid, band_cy, k, w, h, label, style, is_bg=False):
    """가로본: k 는 **왼→오른쪽 진행 칸**, band_cy 는 그 노드가 속한 띠의 중심 y."""
    return N(nid, CX_(k) - w / 2, band_cy - h / 2, w, h, label, style, is_bg)


edges = []


def E(s, d, label, pts, style="", loff=None):
    edges.append(dict(s=s, d=d, label=label, style=style, loff=loff,
                      pts=[(float(a), float(b)) for a, b in pts]))


TOP = lambda nid: nodes[nid]['y']                       # noqa: E731
BOT = lambda nid: nodes[nid]['y'] + nodes[nid]['h']     # noqa: E731
LFT = lambda nid: nodes[nid]['x']                       # noqa: E731
RGT = lambda nid: nodes[nid]['x'] + nodes[nid]['w']     # noqa: E731
MID = lambda nid: nodes[nid]['y'] + nodes[nid]['h'] / 2  # noqa: E731
CXX = lambda nid: nodes[nid]['x'] + nodes[nid]['w'] / 2  # noqa: E731

# ============================================================ 제목
TITLE = ('<b style="font-size:22px">MechDog 통합 AI Flow — A·B·C·D</b>'
         '&nbsp;&nbsp;<span style="font-size:12px;color:#5A6B7D">'
         'MD-AIF-001 <b>v1.2</b> · 2026-09-21 &nbsp;|&nbsp; '
         '<b>레인은 담당자가 아니라 실행 위치(기계)</b> — A 의 추론은 로봇이 아니라 <b>서버 PC</b> 에서 돌고, '
         '<b>모든 MQTT 는 브로커를 지난다</b>(노드끼리 직통 없음). '
         '화살표 위 글자가 <b>그 지점에서 흐르는 데이터</b>다. 업무 순서·분기는 <b>통합 비즈니스 Flow</b> 를 본다</span>'
         '<br><span style="font-size:11px;color:#8FA0B3">'
         '※ <b>보라 = AI 판단</b>(확률적 — 틀릴 수 있다) · <b>파랑 = 규칙 판단</b>(결정적) · '
         '<b>초록 평행사변형 = MQTT 메시지</b>(이름은 <code>schema/topics.json</code> 기준) · '
         '<b>회색 점선 = 자료 미수령</b> · <b>노란 원통 = 참조 데이터</b>(사전·캐시·표 — 흐르지 않고 참조만 한다)'
         '&nbsp;&nbsp;|&nbsp;&nbsp;'
         'A 는 <code>work_docs/A_Flow.png</code> 기준이며 <code>policy.decide()</code> 이후 미수령 · '
         'C 는 카메라를 걷어내고 <b>웨이포인트+거리센서</b>로 전환했다(AI 없음)</span>')
N("title", 30, 8, 1700, 64, TITLE,
  "text;html=1;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;", True)

# 가로 띠 — 상자 크기는 아래에서 **내용에 맞춰** 다시 맞춘다
LANES = [
    ("lnG", 0, 100, 100, 100, "게이트 카메라 <span style='font-size:10px'>ESP32-CAM</span>",
     "#7C3AED", "#FBF8FF", "#D6C2F0"),
    ("lnS", 0, 100, 100, 100, "서버 PC <span style='font-size:10px'>Docker — vision-service · "
     "mosquitto · 보안 판정 · 수집기 · DB</span>", "#2D3E50", "#F7F9FB", "#AEBECE"),
    ("lnV", 0, 100, 100, 100, "방문자 · 현장", "#C98A00", "#FFFDF7", "#E0CB9B"),
    ("lnE", 0, 100, 100, 100, "안내 로봇 본체 <span style='font-size:10px'>ESP32</span>",
     "#2D6CDF", "#F7FAFF", "#B9CDEF"),
    ("lnK", 0, 100, 100, 100, "외부 클라우드 <span style='font-size:10px'>Gemini API</span>",
     "#6B4FA8", "#FBF9FF", "#CFC0E6"),
    ("lnR", 0, 100, 100, 100, "RPi5 <span style='font-size:10px'>STT · 룰 · 멘트 재생</span>",
     "#1E7F4F", "#FAFEFB", "#B4D8C4"),
    ("lnC", 0, 100, 100, 100, "에스코트 노트북 + 로봇 <span style='font-size:10px'>BLE</span>",
     "#8FA0B3", "#FAFBFC", "#CBD3DB"),
    ("lnD", 0, 100, 100, 100, "경고 로봇 <span style='font-size:10px'>2 legs stand + 부저</span>",
     "#B3341C", "#FFFAF9", "#E8BDB4"),
]
MEMBER = {
    "lnG": ["A1"],
    "lnS": ["A2", "A3", "A4", "A5", "A6", "A7", "ST_A", "D1", "D2", "D3", "D4", "D5", "D6",
            "WEB", "D7", "D8", "ST_D", "BRK", "COL", "DB"],
    "lnV": ["V1", "V2", "V3"],
    "lnE": ["E1"],
    "lnK": ["B3"],
    "lnR": ["B1", "B1b", "B2", "B4", "B4b", "B5", "B6", "B7", "ST_B1", "ST_B2", "ST_B3"],
    "lnC": ["C1", "C2", "C3", "ST_C"],
    "lnD": ["ROB"],
}
for lid, lx, lw, ly, lh, name, hc, bfill, bstroke in LANES:
    N(lid + "_b", lx, ly, lw, lh, "",
      "rounded=0;html=1;strokeWidth=1.5;fillColor=%s;strokeColor=%s;" % (bfill, bstroke), True)
    N(lid + "_h", lx, ly - 34, 420, 30, "<b>" + name + "</b>",
      "rounded=0;html=1;strokeWidth=1.5;fontColor=#FFFFFF;fontSize=12;verticalAlign=middle;"
      "align=center;strokeColor=none;fillColor=" + hc + ";", True)

# ============================================================ 방문자
P("V1", cv, 0, NW, 46, "방문자 게이트 도착", S_TERM + C_V)
P("V2", cv, 9, NW, 56, "방문 목적 발화<br><i>\"입고요\" · \"회의 왔는데요\"</i>", S_PROC + C_V)
P("V3", cv, 20, NW, 46, "목적지 도착 · 퇴장", S_TERM + C_V)

# ============================================================ A — 게이트
P("A1", cg, 0, NW, 56,
  "<b>①</b> 스냅샷 촬영 · 전송<br><span style='font-size:9px'>JPEG → 서버(vision-service)</span>",
  S_PROC + C_PROC)
P("A2", ca, 1, NW, 84,
  "<b>②</b> 얼굴 검출 · 대상 선택 <b>MediaPipe</b><br>"
  "<span style='font-size:9px'>face_landmarker · <b>3.0 ms</b> · 0개면 deny<br>"
  "IPD 최대 = 가장 가까운 얼굴<br>"
  "<b>⚠ 배경 통행인까지 세어</b> 정상 통과가 막힌 적 (R-16)</span>", S_PROC + C_AI)
P("A3", ca, 2, NW, 116,
  "<b>③</b> 얼굴 박스 → 정렬 → 임베딩 <b>ArcFace</b><br>"
  "<span style='font-size:9px'>5점 정렬 → w600k_mbf 512-d · <b>5.5 ms</b><br>"
  "<b>⚠ 최대 위험 지점</b> — 정렬이 틀려도 예외가 안 난다<br>"
  "좌우가 뒤바뀌면 통과율 98% → 11.7% (단위 테스트로 안 잡힘)</span>", S_PROC + C_AI)
P("A4", ca, 3, NW, 84,
  "<b>④</b> PPE 검출 <b>GearGuard</b><br>"
  "<span style='font-size:9px'>gear_guard_net.onnx · <b>7.2 ms</b> · 안전모 · 조끼<br>"
  "얼굴 박스 → 전신 추정 크롭 → 192×320<br>"
  "<b>모델 없음·미검출 → 필수 항목 미착용으로 취급</b></span>", S_PROC + C_AI)
P("A5", ca, 4, NW, 54,
  "<b>⑤</b> <b>vision.face</b> · <b>vision.ppe</b> 발행<br>"
  "<span style='font-size:9px'>authorized / unauthorized / undetermined</span>", S_IO + C_MSG)
P("A6", ca, 5, NW, 86, "<b>⑥</b> 인가 AND PPE 통과?", S_DEC + C_RULE)
P("A7", ca, 6, NW, 50,
  "<b>⑦</b> <b>gate.session</b> 발행<br><span style='font-size:9px'>통과자만 B 에게</span>",
  S_IO + C_MSG)

# ============================================================ B — 대화
# 안내 로봇 본체. **판단은 안 하고 신호만 낸다** — RPi5 가 그걸 보고 상태를 옮긴다.
P("E1", cq, 6, NW, 84,
  "<b>터치 · 초음파 · 눈 LED</b><br><span style='font-size:9px'>터치 = 대화 개시 신호 (세션당 1회)<br>초음파 = 재실 확인 · 1.5 m<br>눈 LED = 상태 표시 (AI 아님)</span>", S_PROC + C_PROC)
P("B1", cb, 7, NW, 56,
  "<b>⑧</b> 인사 · 터치 대기<br><span style='font-size:9px'>세션 승계 (BR-B-02)</span>",
  S_WAIT + C_PROC)
P("B1b", cb, 8, NW, 92,
  "<b>⑧-2</b> 오디오 전처리 <i>(STT 앞단)</i><br>"
  "<span style='font-size:9px'>앞 <b>250ms 절단</b> — USB 개시 클릭 (LOG-35)<br>"
  "<b>80Hz 고역통과</b> — 11~19Hz 럼블이 VAD 를 속인다<br>"
  "RMS 0.25 정규화 — 먼 거리 목소리를 들리게</span>", S_PROC + C_RULE)
P("B2", cb, 9, NW, 80,
  "<b>⑨</b> <b>STT</b> whisper.cpp base<br>"
  "<span style='font-size:9px'>엔드포인팅 <b>무음 700ms</b> · <b>약 1,900 ms</b><br>"
  "<i>500ms 로 줄이면 말 도중에 잘린다 (LOG-46)</i><br>"
  "실패해도 예외가 아니다 — 빈 문자열이 온다</span>", S_PROC + C_AI)
P("B3", ck, 10, NW, 82,
  "<b>⑩</b> <b>LLM 분류</b> gemini-flash-lite<br>"
  "<span style='font-size:9px'>목적지 7곳 택1 / null · <b>약 1,000 ms</b><br>"
  "<b>문장을 만들지 않는다</b> — 환각 불가<br><b>인터넷이 끊기면 ⑪ 룰로 떨어진다</b></span>", S_PROC + C_AI)
P("B4", cb, 11, NW, 74,
  "<b>⑪</b> 룰 매칭 (폴백) <i>· 30 ms</i><br>"
  "<span style='font-size:9px'>LLM 이 null·실패일 때만<br>"
  "자모 편집거리 ≤ 2 · <b>모호 판정은 룰만 할 수 있다</b></span>", S_PROC + C_RULE)
P("B4b", cb, 12, NW, 74,
  "<b>⑪-2</b> 신뢰도 산정<br>"
  "<span style='font-size:9px'>0.30·P_stt + 0.50·S_match + 0.20·Margin<br>"
  "<b>≥0.75 일반 확인 · 0.45~0.75 강한 확인 · &lt;0.45 재질문</b></span>",
  S_PROC + C_RULE)
P("B5", cb, 13, NW, 86, "<b>⑫</b> 확인 질의 → 긍정?<br><i>BR-B-10</i>", S_DEC + C_RULE)
P("B6", cb, 14, NW, 100,
  "<b>⑬</b> 에스코트 수락?<br><span style='font-size:9px'>escort.status = <b>idle</b> 일 때만 제안</span>", S_DEC + C_RULE)
P("B7", cb, 15, NW, 54,
  "<b>⑭</b> <b>dialog.result</b> 발행<br>"
  "<span style='font-size:9px'>수락했을 때만 — 거절은 이상이 아니다</span>", S_IO + C_MSG)

# ============================================================ C — 에스코트
# **AI 가 없다.** 원래 카메라 추종이었는데 WiFi 스트림이 불안정해 웨이포인트로 전환했다.
# ArUco 마커 인식 코드는 검증했으나 카메라가 빠지면서 미적용.
P("C1", cc, 17, NW, 74,
  "<b>⑮</b> 웨이포인트 순차 이동<br>"
  "<span style='font-size:9px'><b>시간 기반</b> — 위치를 모른다<br>"
  "노트북 ↔ 로봇은 <b>BLE</b> (MQTT 아님)</span>", S_PROC + C_RULE)
P("C2", cc, 18, NW, 86,
  "<b>⑯</b> 장애물 15cm?<br><i>거리센서</i>", S_DEC + C_RULE)
P("C3", cc, 19, NW, 104,
  "<b>⑰</b> 완주 → 도착 · <b>escort.status</b><br>"
  "<span style='font-size:9px'>인사 동작(scrape_a_bow) · 1 Hz · retain<br>"
  "터치 → <b>출발지 복귀</b>(moving · reception)<br>"
  "<b>복귀를 마친 뒤에야 idle</b><br>"
  "회피 4회 실패 → <b>escort_lost</b></span>", S_IO + C_MSG)

# ============================================================ D — 보안·대시보드
P("D1", cd, 8, NW, 62,
  "<b>㉑</b> session_id 로 얼굴·PPE 결합<br>"
  "<span style='font-size:9px'>둘 중 하나만 와도 판단한다</span>", S_PROC + C_PROC)
P("D2", cd, 9, NW, 96,
  "<b>㉒</b> 상태 판정 <i>(우선순위)</i><br>"
  "<span style='font-size:9px'>unauthorized→ALERT · ppe fail→WARNING<br>"
  "undetermined→PENDING · 그 외 NORMAL</span>", S_DEC + C_RULE)
P("D3", cd, 10, NW, 62,
  "<b>㉓</b> 상태가 <b>바뀌었을 때만</b><br>"
  "<span style='font-size:9px'>같은 판정 반복은 무시 — 중복 경고 방지</span>", S_PROC + C_RULE)
P("D4", cd, 11, NW, 62,
  "<b>㉔</b> <b>alert.event</b> 발행<br>"
  "<span style='font-size:9px'>WARNING→warn · ALERT→critical<br>"
  "<b>PENDING·NORMAL 은 발행 안 함</b></span>", S_IO + C_MSG)
P("D5", cd, 12, NW, 62,
  "<b>㉕</b> <b>robot.command</b>(warning_start)<br>"
  "<span style='font-size:9px'>2 legs stand + 부저 · QoS 1 · retain false</span>",
  S_IO + C_MSG)
P("D6", cd, 13, NW, 56,
  "<b>㉖</b> 대시보드 표시<br>"
  "<span style='font-size:9px'>(session_id, reason) 별로 개별 관리</span>", S_PROC + C_PROC)
P("D7", cw, 15, NW, 86,
  "<b>㉗</b> 관리자가<br>해제?<br><i>자동 해제 없음</i>", S_DEC + C_RULE)
P("D8", cd, 16, NW, 62,
  "<b>㉘</b> <b>resolved=true</b> 발행 +<br><b>warning_clear</b><br>"
  "<span style='font-size:9px'>D 활성 경고가 없을 때만 자세 복귀</span>", S_IO + C_MSG)

# ============================================================ 인프라 (서버 PC)
# **모든 MQTT 는 브로커를 지난다.** 노드끼리 직접 가는 길은 없다 —
# 이걸 안 그리면 레인 사이 화살표가 마치 직통인 것처럼 읽힌다.
N("BRK", 560, BKY, 6100, BKH,
  "<b>MQTT 브로커</b> <span style='font-size:10px'>mosquitto · 서버 PC · :1883 — 노드끼리 직통 없음 · QoS 1 = 사건 · QoS 0+retain = 상태</span>",
  "rounded=0;whiteSpace=wrap;html=1;strokeWidth=2;verticalAlign=middle;align=center;"
  "fillColor=#E3EAF1;strokeColor=#2D3E50;fontColor=#1B2A38;fontSize=13;")
N("COL", CX_(2) - NW / 2, 880 - 31, NW, 62,
  "<b>수집기</b><br><span style='font-size:9px'>구독 전용 — 판정·정규화 없이 원시 수집</span>",
  S_PROC + "fillColor=#FFFFFF;strokeColor=#2D3E50;fontColor=#1B2A38;")
N("DB", CX_(3) - NW / 2, 880 - 40, NW, 80,
  "<b>PostgreSQL</b><br><span style='font-size:9px'>event_logs · system_health<br>"
  "<i>저장 담당 미확정</i></span>",
  "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=10;whiteSpace=wrap;html=1;"
  "strokeWidth=1.5;fontSize=11;fillColor=#FFFFFF;strokeColor=#2D3E50;fontColor=#1B2A38;")

E("BRK", "COL", "전 토픽 구독",
  [(CXX("COL"), BKY + BKH), (CXX("COL"), TOP("COL"))])
E("COL", "DB", "", [(RGT("COL"), MID("COL")), (LFT("DB"), MID("DB"))])

# ============================================================ 관리자 브라우저 · 경고 로봇
P("WEB", cw, 14, NW, 76,
  "<b>대시보드 화면</b><br><span style='font-size:9px'>HTTP 폴링 1초 · A~D 상태 · 활성 경고<br>"
  "<i>브라우저는 MQTT 에 직접 붙지 않는다</i></span>", S_PROC + C_PROC)
P("ROB", cq, 21, 270, 70,
  "<b>경고 자세 + 부저</b><br><span style='font-size:9px'>2 legs stand · ESP32 내장 부저<br>"
  "<i>실행 결과 보고는 미구현</i></span>", S_PROC + C_PROC)

E("D6", "WEB", "HTTP", [(RGT("D6"), cd), (LFT("WEB"), cd)], "dashed=1;")
E("WEB", "D7", "", [(RGT("WEB"), cw), (LFT("D7"), cw)])
E("D5", "BRK", "robot.command", [(CXX("D5"), TOP("D5")), (CXX("D5"), BKY + BKH)])
E("BRK", "ROB", "",
  [(CXX("ROB"), BKY + BKH), (CXX("ROB"), TOP("ROB"))])

# ============================================================ 참조 데이터
# **판단할 때 대조하는 자료**다. 노드 사이를 흐르는 메시지와 다르다 —
# 메시지는 한 번 보내고 끝이지만 이건 계속 있고, 판단할 때마다 조회한다.
# 이게 없으면 "A 가 누구와 대조해서 인가를 판단하나" 가 도면에 안 드러난다.
# 선은 **점선 + 화살표 없음** — 방향이 있는 흐름이 아니라 "이걸 본다" 는 표시다.

N("ST_A", CX_(2) - SW / 2, sa - 76 / 2, SW, 76,
  "<b>등록 얼굴 DB</b><br>EnrollmentStore<br>512-d 임베딩", S_STORE + C_STORE)
N("ST_B1", CX_(9) - SW / 2, sb - 76 / 2, SW, 76,
  "<b>STT 도메인 프롬프트</b><br>입고 도크·회의실…<br><i>한 글자로 인식이 뒤집힌다</i>",
  S_STORE + C_STORE)
N("ST_B2", CX_(11) - SW / 2, sb - 88 / 2, SW, 88,
  "<b>일정표 · 목적지 사전</b><br>schedule.json · destinations.py<br><i>LLM 프롬프트도 여기서</i>", S_STORE + C_STORE)
N("ST_B3", CX_(13) - SW / 2, sb - 76 / 2, SW, 76,
  "<b>멘트 캐시</b><br>tts_cache/*.wav<br><i>합성하지 않는다</i>", S_STORE + C_STORE)
N("ST_C", CX_(17) - SW / 2, sc - 76 / 2, SW, 76,
  "<b>웨이포인트 표</b><br>목적지 → 이동 순서<br><i>시간 기반</i>", S_STORE + C_STORE)
N("ST_D", CX_(9) - SW / 2, sd - 76 / 2, SW, 76,
  "<b>세션별 경고 상태</b><br>(session_id, reason)<br><i>메모리 — DB 아님</i>",
  S_STORE + C_STORE)

# ============================================================ 에지
E("V1", "A1", "", [(CXX("V1"), BOT("V1")), (CXX("A1"), TOP("A1"))])
E("A1", "A2", "JPEG 전송",
  [(RGT("A1"), MID("A1")), (cs, MID("A1")), (cs, TOP("A2"))], loff=(0, -38))
E("A2", "A3", "", [(RGT("A2"), ca), (LFT("A3"), ca)])
E("A3", "A4", "512-d 임베딩", [(RGT("A3"), ca), (LFT("A4"), ca)])
E("A4", "A5", "판정 3값 + PPE", [(RGT("A4"), ca), (LFT("A5"), ca)])
E("A5", "A6", "", [(RGT("A5"), ca), (LFT("A6"), ca)])
E("A6", "A7", "Yes", [(RGT("A6"), ca), (LFT("A7"), ca)])
E("A5", "BRK", "vision.face · vision.ppe",
  [(CXX("A5"), TOP("A5")), (CXX("A5"), BKY + BKH)])
E("BRK", "D1", "", [(CXX("D1"), BKY + BKH), (CXX("D1"), TOP("D1"))])
E("A7", "BRK", "gate.session", [(CXX("A7"), TOP("A7")), (CXX("A7"), BKY + BKH)],
  loff=(-90, -60))
E("BRK", "B1", "", [(CXX("B1"), BKY + BKH), (CXX("B1"), TOP("B1"))])

E("E1", "B1", "터치 · 재실",
  [(CXX("E1"), BOT("E1")), (CXX("E1"), MID("B1")), (LFT("B1"), MID("B1"))], "dashed=1;")
E("B1", "B1b", "터치 → 발화", [(RGT("B1"), cb), (LFT("B1b"), cb)])
E("B1b", "B2", "16 kHz PCM", [(RGT("B1b"), cb), (LFT("B2"), cb)])
E("V2", "B2", "음성", [(CXX("V2"), BOT("V2")), (CXX("B2"), TOP("B2"))], "dashed=1;", loff=(-70, 0))
E("B2", "B3", "텍스트 (HTTPS)",
  [(CXX("B2"), TOP("B2")), (CXX("B2"), MID("B3")), (LFT("B3"), MID("B3"))],
  "dashed=1;", loff=(-96, 0))
E("B3", "B4", "목적지 / null · 실패",
  [(CXX("B3"), BOT("B3")), (CXX("B3"), MID("B4")), (LFT("B4"), MID("B4"))], "dashed=1;")
E("B4", "B4b", "목적지 후보", [(RGT("B4"), cb), (LFT("B4b"), cb)])
E("B4b", "B5", "목적지 + 신뢰도", [(RGT("B4b"), cb), (LFT("B5"), cb)])
E("B5", "B6", "긍정", [(RGT("B5"), cb), (LFT("B6"), cb)])
E("B6", "B7", "네", [(RGT("B6"), cb), (LFT("B7"), cb)])
E("B7", "BRK", "dialog.result", [(CXX("B7"), TOP("B7")), (CXX("B7"), BKY + BKH)])
E("BRK", "C1", "", [(CXX("C1"), BKY + BKH), (CXX("C1"), TOP("C1"))])

E("C1", "C2", "웨이포인트 목록", [(RGT("C1"), cc), (LFT("C2"), cc)])
E("C2", "C3", "", [(RGT("C2"), cc), (LFT("C3"), cc)])
E("C3", "V3", "도착 안내",
  [(RGT("C3"), MID("C3")), (CXX("V3"), MID("C3")), (CXX("V3"), BOT("V3"))])

E("D1", "D2", "세션별 얼굴+PPE", [(RGT("D1"), cd), (LFT("D2"), cd)])
E("D2", "D3", "WARNING · ALERT", [(RGT("D2"), cd), (LFT("D3"), cd)])
E("D3", "D4", "", [(RGT("D3"), cd), (LFT("D4"), cd)])
E("D4", "D5", "", [(RGT("D4"), cd), (LFT("D5"), cd)])
E("D5", "D6", "", [(RGT("D5"), cd), (LFT("D6"), cd)])
E("D7", "D8", "해제", [(RGT("D7"), cd), (LFT("D8"), cd)])

# B·C 가 내는 경고도 같은 토픽으로 D 화면에 모인다 (물리 동작은 없다)
E("B5", "BRK", "alert.event (dialog_failed)",
  [(CXX("B5"), TOP("B5")), (CXX("B5"), BKY + BKH)], "dashed=1;")
E("BRK", "D6", "alert.event — 표시만",
  [(CXX("D6"), BKY + BKH), (CXX("D6"), TOP("D6"))], "dashed=1;")
E("C2", "BRK", "alert.event (escort_lost)",
  [(CXX("C2"), TOP("C2")), (CXX("C2"), BKY + BKH)], "dashed=1;")


E("A3", "ST_A", "", [(CXX("A3"), BOT("A3")), (CXX("A3"), sa)], REF)
E("B2", "ST_B1", "", [(CXX("B2"), BOT("B2")), (CXX("B2"), sb)], REF)
E("B4", "ST_B2", "",
  [(CXX("B4"), BOT("B4")), (CXX("B4"), sb)], REF)
E("B5", "ST_B3", "", [(CXX("B5"), BOT("B5")), (CXX("B5"), sb)], REF)
E("C1", "ST_C", "", [(CXX("C1"), BOT("C1")), (CXX("C1"), sc)], REF)
E("D2", "ST_D", "", [(CXX("D2"), BOT("D2")), (CXX("D2"), sd)], REF)

# ============================================================ 범례 / 미확인 목록
N("note", 60, 1660, 980, 230,
  "<div style='background:#26384F;color:#fff;margin:-6px -6px 6px -8px;padding:4px 8px;"
  "font-size:12px;font-weight:bold'>아직 못 채운 것</div>"
  "<table style='font-size:10px' cellpadding='2'>"
  "<tr><td><b>A</b></td><td><code>policy.decide()</code> 이후 — 무엇을 발행하는지<br>"
  "<span style='color:#8FA0B3'>A_Flow.png 는 판정값을 뽑는 데까지</span></td></tr>"
  "<tr><td><b>C</b></td><td>위치를 모른다 — 시간 기반 웨이포인트<br>"
  "<span style='color:#8FA0B3'>헛걸음해도 로봇이 알 방법이 없다. ArUco 는 카메라와 함께 빠짐</span></td></tr>"
  "<tr><td><b>전체</b></td><td>브로커 IP·네트워크 미합의<br>"
  "<span style='color:#8FA0B3'>ESP32 는 펌웨어에 박혀 있어 바꾸려면 USB 재업로드</span></td></tr>"
  "</table>",
  "rounded=1;arcSize=4;whiteSpace=wrap;html=1;strokeWidth=1.5;align=left;verticalAlign=top;"
  "fontSize=10;spacingLeft=8;spacingTop=6;fillColor=#FBFCFD;strokeColor=#8FA0B3;fontColor=#26384F;",
  True)

# ============================================================ 띠 크기 맞추기
# 상자를 손으로 찍으면 노드를 옮길 때마다 어긋난다. 다 만든 뒤 내용에 맞춰 늘린다.
for _lid, _mem in MEMBER.items():
    _ms = [nodes[m] for m in _mem if m in nodes]
    if not _ms:
        continue
    _x0 = min(m["x"] for _ms_ in [0] for m in _ms) - 24
    _x1 = max(m["x"] + m["w"] for m in _ms) + 24
    _y0 = min(m["y"] for m in _ms) - 18
    _y1 = max(m["y"] + m["h"] for m in _ms) + 18
    _b = nodes[_lid + "_b"]
    _b["x"], _b["y"], _b["w"], _b["h"] = _x0, _y0, _x1 - _x0, _y1 - _y0
    _h = nodes[_lid + "_h"]
    _h["x"], _h["y"] = _x0, _y0 - 34

# ============================================================ 검증 (gen_b_flowchart.py 와 동일 규칙)
LAYERS = {"title"} | {lid + s for lid, *_ in LANES for s in ("_b", "_h")}
OVERLAYS = [(k, nodes[k]) for k in nodes if k in bg and k not in LAYERS]


def rects():
    return [(k, v) for k, v in nodes.items() if k not in bg]


def overlap(a, b, m=6):
    return (a['x'] < b['x'] + b['w'] + m and b['x'] < a['x'] + a['w'] + m and
            a['y'] < b['y'] + b['h'] + m and b['y'] < a['y'] + a['h'] + m)


def text_h(label, w, style):
    import re as _re
    m = _re.search(r"fontSize=(\d+)", style)
    base = int(m.group(1)) if m else 12
    total = 0.0
    for ln in _re.split(r"<br\s*/?>", label):
        segs, pos = [], 0
        for sp in _re.finditer(r"<span[^>]*font-size:(\d+)px[^>]*>(.*?)</span>", ln, _re.S):
            segs.append((_re.sub(r"<[^>]+>", "", ln[pos:sp.start()]), base))
            segs.append((_re.sub(r"<[^>]+>", "", sp.group(2)), int(sp.group(1))))
            pos = sp.end()
        segs.append((_re.sub(r"<[^>]+>", "", ln[pos:]), base))
        px = sum((f * 1.02 if ord(c) > 0x2000 else f * 0.58) for t, f in segs for c in t)
        fs = max([f for t, f in segs if t.strip()] or [base])
        total += max(1, -(-int(px) // max(1, int(w - 10)))) * fs * 1.30
    return total


def label_box(e, fs=10):
    segs, tot = [], 0.0
    for a, b in zip(e['pts'], e['pts'][1:]):
        dd = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        segs.append((a, b, dd))
        tot += dd
    half, acc, lx, ly = tot / 2, 0.0, e['pts'][-1][0], e['pts'][-1][1]
    for a, b, dd in segs:
        if acc + dd >= half:
            t = (half - acc) / dd if dd else 0
            lx, ly = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            break
        acc += dd
    if e.get('loff'):
        lx += e['loff'][0]
        ly += e['loff'][1]
    w = sum((fs * 1.02 if ord(c) > 0x2000 else fs * 0.58) for c in e['label']) + 8
    return dict(x=lx - w / 2, y=ly - 9, w=w, h=18)


def label_dir(e):
    segs, tot = [], 0.0
    for a, b in zip(e['pts'], e['pts'][1:]):
        dd = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        segs.append((a, b, dd))
        tot += dd
    acc = 0.0
    for a, b, dd in segs:
        if acc + dd >= tot / 2:
            return abs(b[1] - a[1]) < abs(b[0] - a[0])
        acc += dd
    return True


rs = rects()
errs_pre = []


def place_labels():
    """글자가 도형을 가리지 않게 라벨을 선과 직각 방향으로 밀어낸다."""
    obstacles = [v for _, v in rs] + [v for _, v in OVERLAYS]
    placed = []
    for e in sorted(edges, key=lambda x: -len(x['label'])):
        if not e['label'].strip():
            continue
        if e.get('loff') is not None:
            placed.append(label_box(e))
            continue
        horiz = label_dir(e)
        for step in range(0, 30):
            d = step * 7
            for off in ([(0, -d), (0, d)] if horiz else [(-d, 0), (d, 0)]):
                e['loff'] = off if d else None
                box = label_box(e)
                if any(overlap(box, o, m=0) for o in obstacles) or \
                   any(overlap(box, q, m=0) for q in placed):
                    continue
                placed.append(box)
                break
            else:
                continue
            break
        else:
            e['loff'] = None
            placed.append(label_box(e))
        if e.get('loff') and abs(e['loff'][0]) + abs(e['loff'][1]) > 80:
            errs_pre.append("LABEL FAR: %s->%s \"%s\" %+d,%+d — 선이 짧아 라벨이 떨어졌다"
                            % (e['s'], e['d'], e['label'], e['loff'][0], e['loff'][1]))


place_labels()
errs = list(errs_pre)

for i in range(len(rs)):
    for j in range(i + 1, len(rs)):
        if overlap(rs[i][1], rs[j][1]):
            errs.append("OVERLAP: %s <-> %s" % (rs[i][0], rs[j][0]))

for k, v in OVERLAYS:
    for k2, v2 in rs:
        if overlap(v, v2, m=0):
            errs.append("OVERLAY: %s covers %s" % (k, k2))

for e in edges:
    if not e['label'].strip():
        continue
    lb = label_box(e)
    for k, v in rs + OVERLAYS:
        if k in (e['s'], e['d']):
            continue        # 양끝은 흰 배경으로 덮고 읽는다 (선에서 떼어내지 않는다)
        if overlap(lb, v, m=0):
            errs.append("LABEL: %s->%s \"%s\" covers %s" % (e['s'], e['d'], e['label'], k))

for k, v in rs:
    if not v['label'].strip():
        continue
    # 원통(cylinder3)은 위아래가 타원이라 **글자가 들어가는 높이가 그만큼 줄어든다.**
    # 이걸 모르고 재면 "여유 17px" 로 통과해 놓고 실물에서는 글자가 테두리에 겹친다.
    if "cylinder" in v['style']:
        pad = 34
    elif "rhombus" in v['style']:
        pad = 26
    else:
        pad = 12
    need = text_h(v['label'], v['w'], v['style'])
    if need > v['h'] - pad:
        errs.append("TEXT OVERFLOW: %s h=%g 필요 %.0f (+%.0f)" % (k, v['h'], need, need - v['h'] + pad))


def seg_hits(p, q, r, m=3):
    return (min(p[0], q[0]) - m < r['x'] + r['w'] and r['x'] < max(p[0], q[0]) + m and
            min(p[1], q[1]) - m < r['y'] + r['h'] and r['y'] < max(p[1], q[1]) + m)


for e in edges:
    for k, v in rs:
        if k in (e['s'], e['d']):
            continue
        for i in range(len(e['pts']) - 1):
            if seg_hits(e['pts'][i], e['pts'][i + 1], v):
                errs.append("EDGE %s->%s seg%d hits %s" % (e['s'], e['d'], i, k))

for e in edges:
    for nid, pt in ((e['s'], e['pts'][0]), (e['d'], e['pts'][-1])):
        n = nodes[nid]
        if not (n['x'] - 4 <= pt[0] <= n['x'] + n['w'] + 4 and
                n['y'] - 4 <= pt[1] <= n['y'] + n['h'] + 4):
            errs.append("ANCHOR %s->%s: (%g,%g) not on %s" % (e['s'], e['d'], pt[0], pt[1], nid))

# 화살표끼리 교차 (같은 노드에서 만나는 분기/합류는 정상이므로 제외)
def seg_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = ccw(p3, p4, p1), ccw(p3, p4, p2)
    d3, d4 = ccw(p1, p2, p3), ccw(p1, p2, p4)
    return (((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and
            ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)))


def polyline_segs(e):
    return [(e['pts'][i], e['pts'][i + 1]) for i in range(len(e['pts']) - 1)]


for i in range(len(edges)):
    for j in range(i + 1, len(edges)):
        e1, e2 = edges[i], edges[j]
        if e1['s'] in (e2['s'], e2['d']) or e1['d'] in (e2['s'], e2['d']):
            continue
        for s1 in polyline_segs(e1):
            for s2 in polyline_segs(e2):
                if seg_intersect(s1[0], s1[1], s2[0], s2[1]):
                    errs.append("CROSS: %s->%s x %s->%s" % (e1['s'], e1['d'], e2['s'], e2['d']))

if errs:
    print("검증 실패 %d건" % len(errs))
    for x in sorted(set(errs)):
        print("  " + x)
    sys.exit(1)
print("검증 통과 — 노드 %d개(배경 %d) / 에지 %d개 · 겹침 0 · 에지-노드 충돌 0 · 에지-에지 교차 0 · 글자 넘침 0 · 라벨 가림 0"
      % (len(nodes), len(bg), len(edges)))

# ============================================================ XML
def frac(n, pt):
    return ((pt[0] - n['x']) / n['w'], (pt[1] - n['y']) / n['h'])


out = ['<mxfile host="app.diagrams.net" version="24.7.17">',
       '  <diagram name="전체 서비스 Flow" id="service-flow">',
       '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" '
       'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2000" '
       'pageHeight="2300" math="0" shadow="0">',
       '      <root>', '        <mxCell id="0" />', '        <mxCell id="1" parent="0" />']

for nid in order:
    n = nodes[nid]
    out.append('        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
               % (nid, html.escape(n['label'], quote=True), n['style']))
    out.append('          <mxGeometry x="%g" y="%g" width="%g" height="%g" as="geometry" />'
               % (n['x'], n['y'], n['w'], n['h']))
    out.append('        </mxCell>')

for i, e in enumerate(edges):
    s, d = nodes[e['s']], nodes[e['d']]
    ex, ey = frac(s, e['pts'][0])
    ix, iy = frac(d, e['pts'][-1])
    st = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;"
          "exitX=%.4f;exitY=%.4f;exitDx=0;exitDy=0;exitPerimeter=0;"
          "entryX=%.4f;entryY=%.4f;entryDx=0;entryDy=0;entryPerimeter=0;"
          "strokeWidth=1.6;fontSize=10;labelBackgroundColor=#FFFFFF;" % (ex, ey, ix, iy)) + e['style']
    out.append('        <mxCell id="e%d" value="%s" style="%s" edge="1" parent="1" '
               'source="%s" target="%s">'
               % (i, html.escape(e['label'], quote=True), st, e['s'], e['d']))
    mid = e['pts'][1:-1]
    if mid or e.get('loff'):
        out.append('          <mxGeometry relative="1" as="geometry">')
        if mid:
            out.append('            <Array as="points">')
            for px, py in mid:
                out.append('              <mxPoint x="%g" y="%g" />' % (px, py))
            out.append('            </Array>')
        if e.get('loff'):
            out.append('            <mxPoint x="%g" y="%g" as="offset" />' % e['loff'])
        out.append('          </mxGeometry>')
    else:
        out.append('          <mxGeometry relative="1" as="geometry" />')
    out.append('        </mxCell>')

out += ['      </root>', '    </mxGraphModel>', '  </diagram>', '</mxfile>', '']

DST = r"D:\Downloads\Mechdog\work_docs\exports\통합_AI_Flow_가로.drawio"
open(DST, "w", encoding="utf-8").write("\n".join(out))
print("저장:", DST)
