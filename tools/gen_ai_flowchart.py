# -*- coding: utf-8 -*-
"""MechDog B **AI Flow** — .drawio 생성 + 겹침/교차 자동 검증.

    PYTHONIOENCODING=utf-8 python tools/gen_ai_flowchart.py

비즈니스 Flow(`gen_b_flowchart.py`)와 **보는 각도가 다르다.**
  비즈니스 Flow  "업무가 어떤 순서로, 어떤 판단 기준으로 흐르는가" — 사람이 따라가는 이야기
  이 문서       "신호가 어떤 부품을 거쳐 어떻게 변환되는가" — 고장을 찾는 지도

그래서 여기서는 **소리 → 파형 → 텍스트 → 의도 → 소리** 의 변환 사슬을 그리고,
각 단계에 **실측 지연**을 붙인다. 어느 단계가 병목인지 도면에서 바로 보여야 한다.

`gen_b_flowchart.py` 와 같은 방식이다 — 좌표를 손으로 찍지 않고 (컬럼, 행)으로 놓으며,
쓰기 전에 겹침·에지 충돌·교차를 검증한다. 통과 못 하면 파일을 쓰지 않는다.
"""
import html
import sys

CY = lambda k: 150 + 118 * k          # noqa: E731
cx = lambda x, w: x + w / 2           # noqa: E731

# ---- 컬럼 --------------------------------------------------------------------
IN_X, IN_W = 60, 210          # 입력 장치
MAIN_X, MAIN_W = 360, 300     # 파이프라인 본류
SIDE_X, SIDE_W = 740, 250     # 곁가지(LLM·일정·캐시)
BUS_X, BUS_W = 1060, 230      # MQTT 버스
OUT_X, OUT_W = 1360, 210      # 출력 장치

cm = cx(MAIN_X, MAIN_W)
cs = cx(SIDE_X, SIDE_W)
cb = cx(BUS_X, BUS_W)

# ---- 스타일 ------------------------------------------------------------------
FONT = "fontSize=11;"
S_TERM = "rounded=1;arcSize=48;whiteSpace=wrap;html=1;strokeWidth=2;" + FONT
S_PROC = "rounded=0;whiteSpace=wrap;html=1;strokeWidth=1.5;" + FONT
S_DEC = "rhombus;whiteSpace=wrap;html=1;strokeWidth=1.5;fontSize=10;"
S_IO = ("shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1;size=18;"
        "whiteSpace=wrap;html=1;strokeWidth=1.5;" + FONT)
S_STORE = ("shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;whiteSpace=wrap;"
           "html=1;strokeWidth=1.5;fontSize=10;")
S_NOTE = ("shape=note;whiteSpace=wrap;html=1;size=14;strokeWidth=1;fontSize=10;"
          "align=left;verticalAlign=top;spacingLeft=4;spacingTop=2;")

C_IN = "fillColor=#FFFDF7;strokeColor=#C98A00;fontColor=#5C3F00;"
C_SIG = "fillColor=#EEF4FA;strokeColor=#2D6CDF;fontColor=#123863;"   # 신호 처리
C_TXT = "fillColor=#F3EEFB;strokeColor=#6B4FA8;fontColor=#3A2560;"   # 텍스트→의도
C_CTL = "fillColor=#F0FBF5;strokeColor=#1E7F4F;fontColor=#0E3D26;"   # 대화 제어
C_IO = "fillColor=#FAFAFA;strokeColor=#5A6B7D;fontColor=#26384F;"
C_HOT = "fillColor=#2D6CDF;strokeColor=#1B4796;fontColor=#FFFFFF;"   # 병목

nodes, order, bg = {}, [], set()


def N(nid, x, y, w, h, label, style, is_bg=False):
    assert nid not in nodes, nid
    nodes[nid] = dict(x=float(x), y=float(y), w=float(w), h=float(h),
                      label=label, style=style)
    order.append(nid)
    if is_bg:
        bg.add(nid)
    return nid


def P(nid, cxx, k, w, h, label, style, is_bg=False):
    return N(nid, cxx - w / 2, CY(k) - h / 2, w, h, label, style, is_bg)


edges = []


def E(s, d, label, pts, style="", loff=None):
    """loff 는 라벨을 경로 중간에서 밀어내는 (dx, dy). 무관한 노드를 덮을 때만 쓴다."""
    edges.append(dict(s=s, d=d, label=label, loff=loff,
                      pts=[(float(a), float(b)) for a, b in pts], style=style))


# ============================================================ 제목
TITLE = ("<b style=\"font-size:22px\">MechDog B — AI Flow (신호 변환 사슬)</b>"
         "&nbsp;&nbsp;<span style=\"font-size:12px;color:#5A6B7D\">"
         "MD-AI-B-001 <b>v2.2</b> · 2026-09-18 · 김별이 &nbsp;|&nbsp; "
         "<b>LLM 분류기 우선 + 룰 폴백</b> · STT <code>whisper.cpp base</code> · "
         "TTS <b>Gemini(Zephyr) 사전 캐싱</b> · 실사람 59문장 해결률 <b>88 %</b></span>"
         "<br><span style=\"font-size:11px;color:#8FA0B3\">"
         "※ 이 도면은 <b>신호가 어떤 부품을 거쳐 어떻게 변환되는가</b>를 그린다 — 고장을 찾는 지도다. "
         "업무 순서·판단 기준은 <b>04_B_비즈니스_Flow</b> 를 본다.&nbsp;&nbsp;"
         "각 단계의 <b>ms 는 RPi5 실기 실측값</b>이며 합계는 <code>NFR-B-101</code>(4,000 ms) 예산과 대조한다.</span>")
N("title", 40, 8, 1500, 64, TITLE,
  "text;html=1;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;", True)

# ============================================================ 계층 배경
BODY_Y, BODY_H = 96, CY(12) + 60 - 96
for nid, x, w, name, col in [
    ("lnIn", IN_X - 16, IN_W + 32, "입력", "fillColor=#FFFDF7;strokeColor=#E0CB9B;"),
    ("lnMain", MAIN_X - 20, MAIN_W + 40, "RPi5 파이프라인 (오디오가 이 박스를 나가지 않는다 — CON-B-03)",
     "fillColor=#FAFCFF;strokeColor=#B8CCE4;"),
    ("lnSide", SIDE_X - 16, SIDE_W + 32, "보조", "fillColor=#FCFAFF;strokeColor=#CBBEE2;"),
    ("lnBus", BUS_X - 16, BUS_W + 32, "MQTT (텍스트만)", "fillColor=#F7FBF9;strokeColor=#B4D8C4;"),
    ("lnOut", OUT_X - 16, OUT_W + 32, "출력", "fillColor=#FFFDF7;strokeColor=#E0CB9B;"),
]:
    N(nid, x, BODY_Y, w, BODY_H, "", "rounded=0;html=1;strokeWidth=1.5;" + col, True)
    N(nid + "_h", x, BODY_Y - 26, w, 24, "<b>" + name + "</b>",
      "text;html=1;align=center;verticalAlign=middle;strokeColor=none;fillColor=none;"
      "fontSize=11;fontColor=#5A6B7D;", True)

# ============================================================ 입력
P("MIC", cx(IN_X, IN_W), 1, IN_W, 76,
  "<b>USB 마이크</b> (MATA C10)<br>16 kHz · 16 bit · mono<br>"
  "<i>plughw: 로 연결 — 카드 번호는 재부팅마다 바뀌어 이름으로 찾는다</i>", S_TERM + C_IN)
P("TOUCH", cx(IN_X, IN_W), 3, IN_W, 56,
  "<b>터치 센서</b> (본체 ESP32)<br>MQTT 상행 · <b>탭 1회 = 청취 시작</b><br><i>FR-B-1003</i>",
  S_TERM + C_IN)
P("ULTRA", cx(IN_X, IN_W), 8, IN_W, 76,
  "<b>초음파</b> (본체 ESP32)<br>1.5 m 이내 = 앞에 있음<br>"
  "<i>발화가 없을 때만 조회 — 3회 연속 미감지로만 부재 확정</i>", S_TERM + C_IN)

# ============================================================ 본류
P("VAD1", cm, 1, MAIN_W, 56,
  "<b>① 1차 VAD</b> (에너지/RMS) &nbsp;<b>&lt; 1 ms</b><br>"
  "배경소음 자동 캘리브레이션 · <i>PTT 모드에서는 우회</i>", S_PROC + C_SIG)
P("TRIM", cm, 2, MAIN_W, 56,
  "<b>②</b> 앞 <b>250 ms 절단</b> &nbsp;<b>0 ms</b><br>"
  "<i>USB 스트림 개시 클릭음 제거 — 안 자르면 정규화·VAD 가 조용히 망가진다 (LOG-35)</i>",
  S_PROC + C_SIG)
P("VAD2", cm, 3, MAIN_W, 62,
  "<b>③ 엔드포인팅</b> (무음 700 ms) &nbsp;<b>700 ms</b><br>"
  "<i>500 ms 로 줄이면 실사람 12건 중 1건이 말 도중에 잘린다 (LOG-46)</i>", S_PROC + C_SIG)
P("STT", cm, 4, MAIN_W, 76,
  "<b>④ STT</b> <code>whisper.cpp base</code> &nbsp;<b>약 1,900 ms</b><br>"
  "language=ko · <b>initial_prompt 도메인 바이어싱</b><br>"
  "<i>최대 병목. 한 글자만 바꿔도 인식이 뒤집힌다 (LOG-52)</i>", S_PROC + C_HOT)
P("LLM", cm, 5, MAIN_W, 92,
  "<b>⑤ LLM 분류기</b> <code>gemini-flash-lite</code> &nbsp;<b>약 1,000 ms</b><br>"
  "목적지 7곳 택1 / 말로만 알려주는 곳 / 일정 매칭 / null<br>"
  "<b>문장을 만들지 않는다</b> — 환각이 구조적으로 불가능", S_PROC + C_TXT)
P("RULE", cm, 6, MAIN_W, 76,
  "<b>⑥ 룰 매칭</b> (폴백) &nbsp;<b>20 ms</b><br>"
  "자모 편집거리 ≤ 2 · 키워드 사전<br>"
  "<i>LLM 이 null·실패일 때만. <b>모호 판정은 룰만 할 수 있다</b></i>", S_PROC + C_TXT)
P("SCORE", cm, 7, MAIN_W, 56,
  "<b>⑦ 신뢰도 산정</b> &nbsp;<b>10 ms</b><br>"
  "0.30·P_stt + 0.50·S_match + 0.20·Margin", S_PROC + C_TXT)
P("DM", cm, 8, MAIN_W, 76,
  "<b>⑧ 대화 관리자</b> (상태 기계) &nbsp;<b>10 ms</b><br>"
  "확인 질의 · 재질문(최대 2회) · 선택형 · 에스코트 제안 · 에스컬레이션<br>"
  "<i>04_B_비즈니스_Flow 의 ①~㉛ 이 여기서 돈다</i>", S_PROC + C_CTL)
P("PICK", cm, 9, MAIN_W, 56,
  "<b>⑨ 멘트 선택</b> &nbsp;<b>0 ms</b><br>"
  "<i>변형이 여럿이면 무작위 — 같은 말이 반복되면 기계 티가 난다</i>", S_PROC + C_CTL)
P("PLAY", cm, 10, MAIN_W, 56,
  "<b>⑩ 재생</b> (wav → ALSA) &nbsp;<b>50 ms</b><br><i>합성하지 않는다. 파일을 틀 뿐이다</i>",
  S_PROC + C_CTL)

# ============================================================ 보조
P("PROMPT", cs, 4, SIDE_W, 56,
  "<b>도메인 프롬프트</b><br>입고 도크 · 출고 도크 · 회의실 …<br>"
  "<i>STT 를 우리 어휘 쪽으로 기울인다</i>", S_STORE + C_SIG)
P("SCHED", cs, 5, SIDE_W, 70,
  "<b>오늘 방문 일정</b> <code>schedule.json</code><br>시각 · 담당자 · 용건 · 장소<br>"
  "<i>\"두 시 반에 오라고 해서요\" 를 푸는 근거. <b>날짜는 검사하지 않는다</b></i>",
  S_STORE + C_TXT)
P("DICT", cs, 6, SIDE_W, 50,
  "<b>목적지 사전</b> <code>destinations.py</code><br>주/보조 키워드 · 장소 이름", S_STORE + C_TXT)
P("CACHE", cs, 9, SIDE_W, 68,
  "<b>음성 캐시</b> <code>~/tts_cache</code> · 51개<br>"
  "Gemini TTS(Zephyr)로 <b>미리</b> 합성<br>"
  "<i>런타임 합성은 3.0~6.7초라 예산을 혼자 넘는다</i>", S_STORE + C_CTL)

# ============================================================ MQTT
P("IN2", cb, 4, BUS_W, 62, "<b>escort.status</b> 수신<br><i>C 가 받을 수 있나 (state=idle)</i>", S_IO + C_IO)
P("IN1", cb, 7, BUS_W, 50, "<b>gate.session</b> 수신<br><i>A → B 세션 인계</i>", S_IO + C_IO)
P("OUT1", cb, 8, BUS_W, 56,
  "<b>dialog.result</b> 발행<br><i>에스코트를 <b>수락했을 때만</b></i>", S_IO + C_IO)
P("OUT2", cb, 9, BUS_W, 50, "<b>alert.event</b> 발행<br><i>이탈 · 실패</i>", S_IO + C_IO)
P("EYE", cb, 6, BUS_W, 50, "<b>눈 LED 상태</b> 발행<br><i>대기·듣는중·처리중·안내중·오류</i>",
  S_IO + C_IO)

# ============================================================ 출력
P("SPK", cx(OUT_X, OUT_W), 10, OUT_W, 62,
  "<b>USB 스피커</b> (TITAN V2)<br><b>152 ms</b> — 재생 명령 → 실제 소리<br>"
  "<i>정합 필터로 실측 (LOG-45)</i>", S_TERM + C_IN)
P("EXT_C", cx(OUT_X, OUT_W), 8, OUT_W, 56,
  "🔗 <b>C · 에스코트</b><br><i>dialog.result 수신 → 동행</i>", S_TERM + C_IO)
P("EXT_D", cx(OUT_X, OUT_W), 9, OUT_W, 50,
  "🔗 <b>D · 보안/대시보드</b><br><i>alert.event 수신</i>", S_TERM + C_IO)
P("BODY", cx(OUT_X, OUT_W), 6, OUT_W, 50, "🔗 <b>본체 ESP32</b><br><i>눈 LED 구동</i>",
  S_TERM + C_IO)

# ============================================================ 예산 메모
N("budget", MAIN_X - 20, CY(11) + 4, MAIN_W + 40 + 330, 96,
  "<b>지연 예산 (NFR-B-101 · 상한 4,000 ms)</b><br>"
  "엔드포인팅 700 + STT 1,900 + LLM 1,000 + 매칭 20 + 판정 10 + 재생 50 + 스피커 152 "
  "&nbsp;=&nbsp; <b>약 3,860 ms</b> &nbsp;(여유 140 ms)<br>"
  "<i>여유가 거의 없다. 모델을 키우면 바로 넘친다 — 늘려야 하면 엔드포인팅(700 ms)이 "
  "가장 먼저 볼 자리지만, 500 ms 로 줄이면 실사람 발화 12건 중 1건이 잘린다.</i>",
  S_NOTE + "fillColor=#FFF9F8;strokeColor=#B3341C;fontColor=#5C1B10;", True)

# ============================================================ 에지
# 좌표를 손으로 찍으면 노드 높이를 바꿀 때마다 앵커가 어긋난다. 경계는 이름으로 가져온다.
TOP = lambda nid: nodes[nid]['y']                      # noqa: E731
BOT = lambda nid: nodes[nid]['y'] + nodes[nid]['h']    # noqa: E731

E("MIC", "VAD1", "", [(270, CY(1)), (360, CY(1))])
E("TOUCH", "VAD2", "PTT — 1차 VAD 우회",
  [(270, CY(3)), (360, CY(3))], "dashed=1;", loff=(0, -59))
E("VAD1", "TRIM", "", [(cm, BOT("VAD1")), (cm, TOP("TRIM"))])
E("TRIM", "VAD2", "", [(cm, BOT("TRIM")), (cm, TOP("VAD2"))])
E("VAD2", "STT", "", [(cm, BOT("VAD2")), (cm, TOP("STT"))])
E("PROMPT", "STT", "", [(SIDE_X, CY(4)), (MAIN_X + MAIN_W, CY(4))], "dashed=1;endArrow=none;")
E("STT", "LLM", "텍스트", [(cm, BOT("STT")), (cm, TOP("LLM"))])
E("SCHED", "LLM", "", [(SIDE_X, CY(5)), (MAIN_X + MAIN_W, CY(5))], "dashed=1;endArrow=none;")
E("LLM", "RULE", "null · 실패 · 타임아웃", [(cm, BOT("LLM")), (cm, TOP("RULE"))])
E("DICT", "RULE", "", [(SIDE_X, CY(6)), (MAIN_X + MAIN_W, CY(6))], "dashed=1;endArrow=none;")
E("RULE", "SCORE", "", [(cm, BOT("RULE")), (cm, TOP("SCORE"))])
E("LLM", "SCORE", "목적지 나옴",
  [(MAIN_X, CY(5)), (330, CY(5)), (330, CY(7)), (MAIN_X, CY(7))],
  loff=(0, -60))   # 기본 위치(경로 중간)가 ⑥ 룰 매칭을 덮는다
E("SCORE", "DM", "", [(cm, BOT("SCORE")), (cm, TOP("DM"))])
E("IN1", "DM", "세션 개시",
  [(BUS_X, CY(7)), (995, CY(7)), (995, CY(8) - 64), (620, CY(8) - 64), (620, TOP("DM"))])
# 세션 개시선보다 **한 칸 아래**로 지나간다 — 같은 높이로 오면 두 선이 겹쳐 달린다.
E("IN2", "DM", "에스코트 가용",
  [(BUS_X, CY(4)), (1035, CY(4)), (1035, CY(8) - 50), (560, CY(8) - 50), (560, TOP("DM"))],
  loff=(-120, 0))
E("ULTRA", "DM", "재실 확인 (발화 없을 때만)",
  [(270, CY(8)), (MAIN_X, CY(8))], "dashed=1;", loff=(0, -63))
E("DM", "OUT1", "확정 + 에스코트 수락", [(MAIN_X + MAIN_W, CY(8)), (BUS_X, CY(8))])
E("DM", "EYE", "상태 전이마다",
  [(MAIN_X + MAIN_W, CY(8) - 20), (1025, CY(8) - 20), (1025, CY(6)), (BUS_X, CY(6))],
  "dashed=1;", loff=(-90, 0))
E("DM", "PICK", "", [(cm, BOT("DM")), (cm, TOP("PICK"))])
E("CACHE", "PICK", "", [(SIDE_X, CY(9)), (MAIN_X + MAIN_W, CY(9))], "dashed=1;endArrow=none;")
E("PICK", "PLAY", "", [(cm, BOT("PICK")), (cm, TOP("PLAY"))])
E("PLAY", "SPK", "", [(MAIN_X + MAIN_W, CY(10)), (OUT_X, CY(10))])
E("OUT1", "EXT_C", "", [(BUS_X + BUS_W, CY(8)), (OUT_X, CY(8))])
E("DM", "OUT2", "이탈 · 실패",
  [(MAIN_X + MAIN_W, CY(8) + 20), (1025, CY(8) + 20), (1025, CY(9)), (BUS_X, CY(9))],
  loff=(0, 16))
E("OUT2", "EXT_D", "", [(BUS_X + BUS_W, CY(9)), (OUT_X, CY(9))])
E("EYE", "BODY", "", [(BUS_X + BUS_W, CY(6)), (OUT_X, CY(6))])

# ============================================================ 검증
# 레인은 노드를 덮는 게 정상이라 면제한다. 주석·범례는 덮으면 안 되므로 검사 대상이다.
LAYERS = {"title", "lnIn", "lnIn_h", "lnMain", "lnMain_h", "lnSide", "lnSide_h",
          "lnBus", "lnBus_h", "lnOut", "lnOut_h"}
OVERLAYS = [(k, nodes[k]) for k in nodes if k in bg and k not in LAYERS]


def rects():
    return [(k, v) for k, v in nodes.items() if k not in bg]


def overlap(a, b, m=6):
    return (a['x'] < b['x'] + b['w'] + m and b['x'] < a['x'] + a['w'] + m and
            a['y'] < b['y'] + b['h'] + m and b['y'] < a['y'] + a['h'] + m)


def seg_hits(p, q, r, m=3):
    x0, y0 = min(p[0], q[0]) - m, min(p[1], q[1]) - m
    x1, y1 = max(p[0], q[0]) + m, max(p[1], q[1]) + m
    if x1 < r['x'] or x0 > r['x'] + r['w'] or y1 < r['y'] or y0 > r['y'] + r['h']:
        return False
    if abs(p[0] - q[0]) < 1e-6:                     # 수직
        return r['x'] + m < p[0] < r['x'] + r['w'] - m
    if abs(p[1] - q[1]) < 1e-6:                     # 수평
        return r['y'] + m < p[1] < r['y'] + r['h'] - m
    return True


def polyline_segs(e):
    pts = e['pts']
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def frac(n, pt):
    return ((pt[0] - n['x']) / n['w'], (pt[1] - n['y']) / n['h'])


def text_h(label, w, style):
    """라벨을 폭 w 에 넣었을 때 필요한 세로 픽셀. drawio 는 넘쳐도 말없이 삐져나온다."""
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
        rows = max(1, -(-int(px) // max(1, int(w - 10))))
        total += rows * fs * 1.30
    return total


errs = []
rs = rects()
def label_box(e, fs=10):
    """drawio 기본 라벨 위치(경로 중간) + loff"""
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
    """라벨이 얹히는 선분이 가로면 True — 가로선의 글자는 선 위/아래로 피한다"""
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


errs_pre = []


def place_labels():
    """**글자가 도형을 가리지 않게** 라벨을 밀어낸다.

    drawio 기본 위치(경로 중간)는 노드가 촘촘하면 도형 위에 얹힌다. 흰 배경으로
    읽히기는 해도 밑의 글자를 지운다. 여기서 충돌이 없어질 때까지 선과 **직각 방향**으로
    밀어내고, 끝내 자리가 없으면 검증에서 실패로 잡힌다(그때는 행 간격을 벌려야 한다).
    """
    obstacles = [v for _, v in rs] + [v for _, v in OVERLAYS]
    placed = []
    for e in sorted(edges, key=lambda x: -len(x['label'])):
        if not e['label'].strip():
            continue
        if e.get('loff') is not None:        # 손으로 지정한 위치는 그대로 둔다
            placed.append(label_box(e))
            continue
        horiz = label_dir(e)
        ends = (nodes[e['s']], nodes[e['d']])
        # 1단계 — **30px 안에서** 아무것도 안 가리는 자리를 찾는다.
        # 멀리 밀어내면 어느 화살표의 라벨인지 알 수 없게 된다(63px 까지 간 적이 있다).
        found = False
        for step in range(0, 5):
            d = step * 7
            for off in ([(0, -d), (0, d)] if horiz else [(-d, 0), (d, 0)]):
                e['loff'] = off if d else None
                box = label_box(e)
                if any(overlap(box, o, m=0) for o in obstacles):
                    continue
                if any(overlap(box, q, m=0) for q in placed):
                    continue
                placed.append(box)
                found = True
                break
            if found:
                break
        if found:
            continue
        # 2단계 — 못 찾았으면 **선 바로 위**에 붙인다. 자기 양끝 노드는 가려도 된다.
        # `labelBackgroundColor=#FFFFFF` 로 흰 바탕이 깔려 글자는 읽힌다.
        e['loff'] = (0, -13) if horiz else (-13, 0)
        placed.append(label_box(e))
        if e.get('loff') and abs(e['loff'][0]) + abs(e['loff'][1]) > 30:
            errs_pre.append("LABEL FAR: %s->%s \"%s\" %+d,%+d — 선이 짧아 라벨이 떨어졌다"
                            % (e['s'], e['d'], e['label'], e['loff'][0], e['loff'][1]))


place_labels()
errs_extra = list(errs_pre)


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
    if not v['label'].strip() or "ellipse" in v['style']:
        continue
    pad = 26 if "rhombus" in v['style'] else 12
    need = text_h(v['label'], v['w'], v['style'])
    if need > v['h'] - pad:
        errs.append("TEXT OVERFLOW: %s h=%g 필요 %.0f (+%.0f)" % (k, v['h'], need, need - v['h'] + pad))

for i in range(len(rs)):
    for j in range(i + 1, len(rs)):
        if overlap(rs[i][1], rs[j][1]):
            errs.append("OVERLAP: %s <-> %s" % (rs[i][0], rs[j][0]))

for e in edges:
    for k, (p, q) in enumerate(polyline_segs(e)):
        for nid, r in rs:
            if nid in (e['s'], e['d']):
                continue
            if seg_hits(p, q, r):
                errs.append("EDGE %s->%s seg%d hits %s" % (e['s'], e['d'], k, nid))

for e in edges:
    for end, nid in ((e['pts'][0], e['s']), (e['pts'][-1], e['d'])):
        n = nodes[nid]
        fx, fy = frac(n, end)
        if not (-0.02 <= fx <= 1.02 and -0.02 <= fy <= 1.02):
            errs.append("ANCHOR %s->%s: point (%s,%s) not on %s boundary"
                        % (e['s'], e['d'], end[0], end[1], nid))

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
    for m in sorted(set(errs)):
        print("  " + m)
    sys.exit(1)

print("검증 통과 — 노드 %d개(배경 %d) / 에지 %d개 · 겹침 0 · 에지-노드 충돌 0 · 글자 넘침 0 · 라벨 가림 0"
      % (len(nodes), len(bg), len(edges)))

# ============================================================ 출력
out = ['<mxfile host="app.diagrams.net">',
       '  <diagram name="B AI Flow">',
       '    <mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" '
       'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
       'pageWidth="1654" pageHeight="1169" math="0" shadow="0">',
       '      <root>',
       '        <mxCell id="0" />',
       '        <mxCell id="1" parent="0" />']

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
          "strokeWidth=1.6;fontSize=10;labelBackgroundColor=#FFFFFF;"
          % (ex, ey, ix, iy)) + e['style']
    out.append('        <mxCell id="e%d" value="%s" style="%s" edge="1" parent="1" '
               'source="%s" target="%s">' % (i, html.escape(e['label'], quote=True), st,
                                             e['s'], e['d']))
    mid = e['pts'][1:-1]
    if mid:
        out.append('          <mxGeometry relative="1" as="geometry">')
        out.append('            <Array as="points">')
        for px, py in mid:
            out.append('              <mxPoint x="%g" y="%g" />' % (px, py))
        out.append('            </Array>')
        if e.get('loff'):
            out.append('            <mxPoint x="%g" y="%g" as="offset" />' % e['loff'])
        out.append('          </mxGeometry>')
    elif e.get('loff'):
        out.append('          <mxGeometry relative="1" as="geometry">')
        out.append('            <mxPoint x="%g" y="%g" as="offset" />' % e['loff'])
        out.append('          </mxGeometry>')
    else:
        out.append('          <mxGeometry relative="1" as="geometry" />')
    out.append('        </mxCell>')

out += ['      </root>', '    </mxGraphModel>', '  </diagram>', '</mxfile>', '']

DST = r"D:\Downloads\Mechdog\work_docs\exports\B_AI_Flow.drawio"
open(DST, "w", encoding="utf-8").write("\n".join(out))
print("저장: " + DST)
