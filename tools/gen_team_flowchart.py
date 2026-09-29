# -*- coding: utf-8 -*-
"""MechDog **팀 통합 Flow** — A·B·C·D 를 한 장에. .drawio 생성 + 자동 검증.

    PYTHONIOENCODING=utf-8 python tools/gen_team_flowchart.py

`gen_b_flowchart.py` 를 복사해 **A·C·D 점선 스텁 자리를 실제 흐름으로 채운 것**이다.
B 는 그대로 상세하고, 나머지 셋은 **판단 지점과 주고받는 메시지**만 그린다 —
셋까지 B 수준으로 그리면 150 노드가 되어 아무도 안 읽는다. 내부 상세는 담당자 도면에 있다.

**출처**
  A  `work_docs/A_Flow.png` (여도훈) — 모델·지연. `policy.decide()` 이후는 미수령
  B  `dialog/` 실제 코드
  C  `work_docs/DogC_Flow_최신.md` (최현수, 09-14). **PPT(09-07)는 구버전이라 쓰지 않는다**
  D  `origin/feature/security-dashboard` 실제 코드 (백경률)

원본(B 전용)은 `gen_b_flowchart.py` 다. 둘은 갈라져 있으므로 B 흐름이 바뀌면 양쪽을 고친다.

**좌표를 손으로 찍지 않는다.** 노드는 (컬럼, 행) 으로 놓고 화살표는 노드 경계를 가져오는
헬퍼로 잇는다. 그래서 노드를 하나 넣어도 나머지가 알아서 따라간다 — 예전에 "레이아웃이
포화라 못 넣는다" 고 판단했던 것은 이 구조를 잊고 XML 을 직접 본 탓이다.

돌리면 **검증이 먼저 돈다.** 통과 못 하면 파일을 쓰지 않는다.
  - 노드끼리 겹치는지            - 화살표가 무관한 노드를 가로지르는지
  - 화살표 끝이 노드에 붙었는지   - 화살표끼리 교차하는지

같은 방식을 A·C·D 도 쓰도록 work_docs/팀원용_drawio_프롬프트.md 로 배포했다.

**도면의 원본은 XML 이 아니라 이 스크립트다.** XML 을 직접 고치면 다음 생성 때 덮어써진다.
2026-09-18 에 세션 임시 폴더에서 저장소로 옮겼다 — 날아가면 92KB XML 을 손으로 고쳐야 한다.
"""
import html, sys

CY = lambda k: 170 + 150 * k

# ---- 컬럼 좌표 --------------------------------------------------------------
VX, VW = 40, 170        # 방문자        cx 160
AX, AW = 340, 220       # A 게이트      cx 450
B1, B2, B3, B4 = 680, 980, 1280, 1580
BW1 = BW2 = BW3 = 220
BW4 = 240
C1X, C1W = 1960, 320    # C            cx 2070
DX, DW = 2670, 330      # D            cx 2380
LOOPX = 613             # 좌측 연결자 코리도
CORR1, CORR2, CORR3 = 918, 1218, 1518   # b1|b2, b2|b3, b3|b4 사이 코리도 (원 44px)

cx = lambda x, w: x + w / 2

# ---- 스타일 ----------------------------------------------------------------
FONT = "fontSize=11;"
S_TERM = "rounded=1;arcSize=48;whiteSpace=wrap;html=1;strokeWidth=2;" + FONT
S_PROC = "rounded=0;whiteSpace=wrap;html=1;strokeWidth=1.5;" + FONT
S_DEC = "rhombus;whiteSpace=wrap;html=1;strokeWidth=1.5;fontSize=10;"
S_IO = "shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1;size=18;whiteSpace=wrap;html=1;strokeWidth=1.5;" + FONT
S_PRE = ("shape=process;whiteSpace=wrap;html=1;backgroundOutline=1;size=0.08;"
         "strokeWidth=1.5;" + FONT)
S_CIRC = ("ellipse;whiteSpace=wrap;html=1;strokeWidth=2;fontSize=15;fontStyle=1;"
          "verticalAlign=middle;align=center;")
S_NOTE = ("shape=note;whiteSpace=wrap;html=1;size=14;strokeWidth=1;fontSize=10;"
          "align=left;verticalAlign=top;spacingLeft=4;spacingTop=2;")
S_PANEL = ("rounded=1;arcSize=4;whiteSpace=wrap;html=1;strokeWidth=1.5;align=left;"
           "verticalAlign=top;fontSize=10;spacingLeft=8;spacingTop=6;spacingRight=6;")
S_GROUP = ("rounded=1;arcSize=6;dashed=1;dashPattern=8 6;strokeWidth=2;html=1;"
           "verticalAlign=top;align=center;fontSize=12;fontStyle=1;spacingTop=4;")

# 색
CV = "fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5A3D00;"
CA = "fillColor=#E7F0FF;strokeColor=#2D6CDF;fontColor=#123863;"
CB = "fillColor=#FFFFFF;strokeColor=#1E7F4F;fontColor=#10331F;"
CBD = "fillColor=#F2FAF5;strokeColor=#1E7F4F;fontColor=#10331F;"
CBIO = "fillColor=#DFF3E8;strokeColor=#1E7F4F;fontColor=#10331F;"
CC = "fillColor=#EDEEFF;strokeColor=#5B5BD6;fontColor=#22225C;"
CD = "fillColor=#FDEBE8;strokeColor=#B3341C;fontColor=#5C1B10;"
CEND = "fillColor=#E9EDF2;strokeColor=#5A6B7D;fontColor=#26384F;"
CDATA = "fillColor=#F0F1F5;strokeColor=#5A6B7D;fontColor=#26384F;"
CCIRC_A = "fillColor=#FFFFFF;strokeColor=#1E7F4F;fontColor=#1E7F4F;"
CCIRC_B = "fillColor=#FFFFFF;strokeColor=#C98A00;fontColor=#C98A00;"
CCIRC_D = "fillColor=#FFFFFF;strokeColor=#B3341C;fontColor=#B3341C;"
CCIRC_L = "fillColor=#FFFFFF;strokeColor=#5A6B7D;fontColor=#5A6B7D;"

# 외부 인터페이스 스텁(다른 담당자 도면과 병합될 자리) 전용 스타일 — 일부러 흐리게, 점선 테두리
S_EXT = ("rounded=1;arcSize=16;dashed=1;dashPattern=6 4;whiteSpace=wrap;html=1;"
         "strokeWidth=1.5;fontSize=10;fillColor=#F3F4F6;strokeColor=#8FA0B3;fontColor=#5A6B7D;")

nodes = {}      # id -> dict
order = []
bg = set()      # 검증 제외 (레인/그룹/패널 배경)


def N(nid, x, y, w, h, label, style, is_bg=False):
    assert nid not in nodes, nid
    nodes[nid] = dict(x=float(x), y=float(y), w=float(w), h=float(h),
                      label=label, style=style)
    order.append(nid)
    if is_bg:
        bg.add(nid)
    return nid


def P(nid, cxx, k, w, h, label, style, is_bg=False):
    """행 k 중심 배치"""
    return N(nid, cxx - w / 2, CY(k) - h / 2, w, h, label, style, is_bg)


# 노드 경계를 이름으로 가져온다 — 높이를 바꿔도 화살표가 따라온다
TOP = lambda nid: nodes[nid]['y']                       # noqa: E731
BOT = lambda nid: nodes[nid]['y'] + nodes[nid]['h']     # noqa: E731
MID = lambda nid: nodes[nid]['y'] + nodes[nid]['h'] / 2  # noqa: E731
CXX = lambda nid: nodes[nid]['x'] + nodes[nid]['w'] / 2  # noqa: E731  — 가로 중앙
LFT = lambda nid: nodes[nid]['x']                       # noqa: E731
RGT = lambda nid: nodes[nid]['x'] + nodes[nid]['w']     # noqa: E731

edges = []      # (src, dst, label, style, [절대 폴리라인 점들])


def E(s, d, label, pts, style="", loff=None):
    """loff 는 라벨을 경로 중간에서 밀어내는 (dx, dy). 라벨이 무관한 노드를 덮을 때만 쓴다."""
    edges.append(dict(s=s, d=d, label=label, pts=[(float(a), float(b)) for a, b in pts],
                      style=style, loff=loff))


# ============================================================ 제목 / 레인
TITLE = ("<b style=\"font-size:22px\">MechDog 팀 통합 Flow — A·B·C·D</b>"
         "&nbsp;&nbsp;<span style=\"font-size:12px;color:#5A6B7D\">"
         "MD-TF-001 <b>v1.0</b> · 2026-09-21 · 김별이 &nbsp;|&nbsp; "
         "<b>에스코트는 선택 — 위치를 말로 알려주고 물어본 뒤 수락해야 C 에게 넘긴다(㉖-2~㉖-4)</b> · "
         "<b>⑭-2 LLM 분류 폴백</b>(룰이 모를 때만) · "
         "목적지 <b>7곳</b>(<code>reception</code> 제외 — B 가 안내데스크에 서 있다) · "
         "STT <b>whisper base</b> · 터치 PTT(⑥-2·⑥-3) · "
         "초음파는 발화가 없을 때만(⑧-2·⑰-2)</span>"
         "<br><span style=\"font-size:11px;color:#8FA0B3\">"
         "※ 이 도면은 <b>B(김별이) 담당 범위만</b> 상세히 그린다. A·C·D는 각 담당자(여도훈·최현수·백경률)의 "
         "도면을 그대로 이어붙일 <b>점선 스텁 박스</b>로만 표시했다.&nbsp;&nbsp;"
         "노드 안의 『』 는 <b>실제로 나가는 멘트</b>다 — 전체 문구는 <code>dialog/phrases.json</code>. "
         "위치 설명(\"오른쪽 통로 끝\" 등)은 <b>시연장 배치가 정해지면 교체해야 하는 임시값</b>이다.</span>")
N("title", 40, 8, 2500, 68, TITLE,
  "text;html=1;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;", True)

LANE_Y, LANE_H = 86, 44
# C 가 row 29 까지 내려간다(대기→회피→도착→터치 8초→복귀). 레인이 그보다 짧으면
# 노드가 배경 밖으로 삐져나온다. 가장 아래 노드 + 여백에 맞춘다.
BODY_Y, BODY_H = 130, 3920        # 130 .. 4050
LANES = [
    ("lnV", 30, 190, "방문자", "fillColor=#C98A00;", "fillColor=#FFFDF7;strokeColor=#E0CB9B;"),
    ("lnA", 240, 356, "A · 게이트 (여도훈)", "fillColor=#7C3AED;", "fillColor=#FBF8FF;strokeColor=#D6C2F0;"),
    ("lnB", 600, 1300, "B · 대화 (김별이) — 이 도면에서 유일하게 상세하다",
     "fillColor=#1E7F4F;", "fillColor=#FAFEFB;strokeColor=#B4D8C4;"),
    ("lnC", 1940, 640, "C · 에스코트 (최현수)", "fillColor=#5B5BD6;",
     "fillColor=#FBFBFE;strokeColor=#C6C6EC;"),
    ("lnD", 2620, 460, "D · 보안·대시보드 (백경률)", "fillColor=#B3341C;",
     "fillColor=#FFFAF9;strokeColor=#E8BDB4;"),
]
for lid, lx, lw, lname, hstyle, bstyle in LANES:
    N(lid + "_b", lx, BODY_Y, lw, BODY_H, "", "rounded=0;html=1;strokeWidth=1.5;" + bstyle, True)
    N(lid + "_h", lx, LANE_Y, lw, LANE_H, "<b>" + lname + "</b>",
      "rounded=0;html=1;strokeWidth=1.5;fontColor=#FFFFFF;fontSize=14;verticalAlign=middle;align=center;strokeColor=none;" + hstyle, True)

# ============================================================ 방문자 (B와 직접 접하는 구간만)
P("V1", 125, 0, VW, 50, "방문자 게이트 도착", S_TERM + CV)
P("V2", 125, 9, VW, 64, "방문 목적 발화<br><i>\"입고요\" / \"도크 갈게요\"</i>", S_PROC + CV)
P("V3", 125, 17, VW, 64, "확인 질의에 응답<br><i>긍정 7종 / 부정 5종 / 무응답</i>", S_PROC + CV)

# ============================================================ A 인터페이스 (외부 스텁 — 내부 프로세스는 여도훈 도면)
CA_AI = "fillColor=#F3E8FF;strokeColor=#7C3AED;fontColor=#3B0764;strokeWidth=2.5;"
CA_DENY = "fillColor=#FDEBE8;strokeColor=#B3341C;fontColor=#5C1B10;"

# A — `work_docs/A_Flow.png`(여도훈) 그대로. 신원(좌)·PPE(우) 두 갈래가 **병렬**로 돈다.
#
# **B 와 같은 방식으로 배치한다** — 행 번호를 주면 y 가 계산되고 높이도 통일한다.
# 손으로 y 를 찍으면 간격이 제각각이 되어 몰려 보인다. B 는 CY(k)=170+130k 를 쓰는데
# A 는 12 노드를 B01(y 671) 위에 넣어야 해서 간격만 좁게 잡은 별도 공식을 쓴다.
ACY = lambda k: 200 + 165 * k       # noqa: E731  — A 전용 행 공식
AH = 82                             # 모든 A 노드 같은 높이
ALX, ARX, AW2 = 250, 424, 160       # 좌·우 두 열
AMX, AMW = 250, 334                 # 본류(합류) 한 줄


def PA(nid, k, label, style, x=AMX, w=AMW):
    """A 레인 노드. 행 번호 k 로 놓고 높이는 AH 로 고정한다."""
    return N(nid, x, ACY(k) - AH / 2, w, AH, label, style)


PA("A1", 0, "<b>A-①</b> JPEG 디코드<br>"
   "<span style='font-size:9px'>payload.snapshot (base64) · 실패 → deny</span>", S_PROC + CA)
PA("A2", 1, "<b>A-②</b> 얼굴 검출 <i>[AI]</i><br>"
   "<span style='font-size:9px'>MediaPipe · <b>3.0ms</b> · 0개 → deny</span>", S_PROC + CA_AI)
PA("A3", 2, "<b>A-③</b> 대상 선택 · 근접 인원 계수<br>"
   "<span style='font-size:9px'>IPD 최대 · <i>배경 통행인까지 세던 결함 (R-16)</i></span>",
   S_PROC + CA)

PA("A4", 3, "<b>A-④</b> 5점 정렬<br>"
   "<span style='font-size:9px'>112×112 · <i>틀려도 예외 없음</i></span>",
   S_PROC + CA_AI, ALX, AW2)
PA("A5", 4, "<b>A-⑤</b> 임베딩 <i>[AI]</i><br>"
   "<span style='font-size:9px'>512-d · <b>5.5ms</b></span>", S_PROC + CA_AI, ALX, AW2)
PA("A6", 5, "<b>A-⑥</b> 등록 대조<br>"
   "<span style='font-size:9px'>코사인 top-1 · 불일치 deny</span>", S_PROC + CA, ALX, AW2)

PA("A7", 3, "<b>A-⑦</b> 전신 크롭<br>"
   "<span style='font-size:9px'>body_from_face()</span>", S_PROC + CA, ARX, AW2)
PA("A8", 4, "<b>A-⑧</b> 리사이즈<br>"
   "<span style='font-size:9px'>192×320 · /255</span>", S_PROC + CA, ARX, AW2)
PA("A9", 5, "<b>A-⑨</b> PPE 검출 <i>[AI]</i><br>"
   "<span style='font-size:9px'>gear_guard · <b>7.2ms</b></span>", S_PROC + CA_AI, ARX, AW2)

PA("A10", 6, "<b>A-⑩</b> <b>SnapshotEvidence</b> 결합<br>"
   "<span style='font-size:9px'>person_id · score · ppe · proximity · error</span>", S_PROC + CA)
PA("A11", 7, "<b>A-⑪</b> <b>policy.decide()</b> → 발행<br>"
   "<span style='font-size:9px'><b>vision.face · vision.ppe</b> (+ gate.session)</span>",
   S_IO + CBIO)
PA("A12", 8, "<b>A-⑫</b> deny — 대화 미개시<br>"
   "<span style='font-size:9px'>미인가 · PPE 미착용 · <b>undetermined 는 재촬영</b></span>",
   S_PROC + CA_DENY)

# ============================================================ B — 본류
cb1 = cx(B1, BW1)   # 790
cb2 = cx(B2, BW2)   # 1090
cb3 = cx(B3, BW3)   # 1390
cb4 = cx(B4, BW4)   # 1700

P("B01", cb1, 2, BW1, 50, "<b>①</b> 세션 인계 수신 <b>gate.session</b><br><i>session_id 무변경 승계 (BR-B-02)</i>", S_TERM + CB)
P("B06", cb1, 5, BW1, 76, "<b>⑥</b> 인사 · 방문목적 질의 <i>· attempt = 1</i><br><span style='font-size:9px'>『반가워요. 터치하고<br>모르는 길을 물어보세요』</span>", S_PROC + CB)
P("B06b", cb1, 6, BW1, 88, "<b>⑥-2</b> 터치 대기 <i>· 세션당 1회</i><br>"
  "<span style='font-size:9px'>본체 터치 센서(Touch_Pin 33) · 최대 15초<br>"
  "<b>재질문·확인 질의는 터치 없이 바로 듣는다</b></span>",
  S_PRE + "fillColor=#EEF4FA;strokeColor=#2D6CDF;fontColor=#123863;")
P("B06c", cb1, 7, BW1, 100, "<b>⑥-3</b> 터치<br>감지?", S_DEC + "fillColor=#EEF4FA;strokeColor=#2D6CDF;fontColor=#123863;")
P("B07", cb1, 8, BW1, 88, "<b>⑦</b> 청취 LISTENING · <b>STT 시작</b><br>"
  "<span style='font-size:9px'><b>♪</b>시작 → 무음 700ms → <b>♪</b>끝 → 연산 → <b>♪</b> → 발화<br>"
  "80Hz 고역통과 — 럼블을 안 깎으면 헛인식</span>", S_PRE + CB)
P("B08", cb1, 9, BW1, 100, "<b>⑧</b> 터치 구간 내<br>발화 감지?", S_DEC + CBD)
P("B08b", cb2, 9, BW2, 100, "<b>⑧-2</b> 앞에 사람이<br>있나?<br><i>초음파 · <b>3회 연속</b> 미감지일 때만 없음</i>", S_DEC + CBD)
P("B09", cb3, 9, BW3, 76, "<b>⑨</b> 재촉 1회 <i>· 횟수 미포함 (BR-B-06)</i><br><span style='font-size:9px'>『방문이 처음이신가요?<br>터치하고 안내를 받아보세요』</span>", S_PROC + CB)
P("B10", cb3, 10, BW3, 100, "<b>⑩</b> 재촉 후 15초 내<br>터치 + 발화?", S_DEC + CBD)
P("B11", cb4, 10, BW4, 64, "<b>⑪</b> 이탈 판정<br><b>alert.event</b>(level=info)", S_PROC + CB)
N("EX2", 1870, CY(10) - 25, 240, 50, "세션 종료 · IDLE 복귀", S_TERM + CEND)
P("B12", cb1, 10, BW1, 64, "<b>⑫</b> 2차 VAD → STT <b>whisper <b>base</b></b><br><i>+ 도메인 보정 (FR-B-302)</i>", S_PROC + CB)
P("B13", cb1, 11, BW1, 64, "<b>⑬</b> 목적지 <b>7곳</b> 키워드 매핑<br>+ 신뢰도 산정", S_PROC + CB)
P("B14", cb1, 12, BW1, 100, "<b>⑭</b> 목적지 후보<br>2개 이상?", S_DEC + CBD)
P("B15", cb2, 12, BW2, 76,
  "<b>⑮</b> 선택형 재질문 <i>· 횟수 미포함 (BR-B-04)</i><br>"
  "<span style='font-size:9px'>『입고 도크와 출고 도크 중<br>어디로 가시나요?』</span>", S_PROC + CB)
P("B15b", cb3, 12, BW3, 100, "<b>⑮-2</b> 선택형 재질문<br>3회 도달?<br><i>무한 반복 방지</i>", S_DEC + CBD)
P("B14b", cb1, 13, BW1, 76,
  "<b>⑭-2</b> <b>LLM 분류 폴백</b> (후보 0개일 때)<br>"
  "<i>8곳 택1 또는 null · 문장 생성 안 함</i><br>"
  "<span style='font-size:9px'>실패·타임아웃이면 ⑰ 재질문 — 대화는 멈추지 않는다</span>",
  S_DEC + "fillColor=#F3EEFB;strokeColor=#6B4FA8;fontColor=#3A2560;")
P("B16", cb1, 14, BW1, 100, "<b>⑯</b> 후보 1개 AND<br>신뢰도 ≥ 0.45?", S_DEC + CBD)
P("B17", cb2, 14, BW2, 100, "<b>⑰</b> 시도 &lt; 3회?<br><i>BR-B-05</i>", S_DEC + CBD)
P("B17b", cb3, 14, BW3, 100, "<b>⑰-2</b> 앞에 사람이<br>있나?<br><i>없으면 재질문하지 않는다</i>", S_DEC + CBD)
P("B18", cb4, 14, BW4, 92,
  "<b>⑱</b> 재질문 · <i>attempt += 1</i><br>"
  "<span style='font-size:9px'>1차 『잘 못 들었어요. 한 번 더 말씀해 주세요』<br>"
  "2차 『어디로 가시는지 한 번만 더 말씀해 주세요』</span>", S_PROC + CB)
P("B19", cb3, 15, BW3, 76,
  "<b>⑲</b> 실패 안내 → 에스컬레이션<br>"
  "<span style='font-size:9px'>『못 알아들어서 죄송해요.<br>담당 직원을 불러 드릴게요』</span>", S_PROC + CB)
P("B20", cb1, 15, BW1, 100, "<b>⑳</b> 신뢰도 ≥ 0.75?", S_DEC + CBD)
P("B21", cb1, 16, BW1, 76,
  "<b>㉑</b> 확인 질의 <i>(목적지별 고정문)</i><br>"
  "<span style='font-size:9px'>『목적지가 입고 도크 이신가요?』</span>", S_PROC + CB)
P("B22", cb2, 16, BW2, 76,
  "<b>㉒</b> 강한 확인 질의<br><span style='font-size:9px'>㉑ 과 같은 캐시 멘트를 쓴다 —<br>"
  "런타임 합성은 인터넷이 필요해 불가</span>", S_PROC + CB)
P("B23", cb1, 17, BW1, 100, "<b>㉓</b> 응답 판정?", S_DEC + CBD)
P("B26", cb1, 18, BW1, 64, "<b>㉖</b> 목적지 확정 CONFIRMED<br><i>확인 없이 확정 금지 (BR-B-03)</i>", S_PROC + CB)
P("B26b", cb1, 19, BW1, 88,
  "<b>㉖-2</b> <b>위치 음성 안내</b><br>"
  "<span style='font-size:9px'>『입고 도크는 오른쪽 통로 끝에 있어요.<br>"
  "<b>직접 안내해 드릴까요?</b>』</span>", S_PROC + "fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5C3F00;")
P("B26c", cb1, 20, BW1, 100, "<b>㉖-3</b> 에스코트<br>수락?", S_DEC + "fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5C3F00;")
P("B26d", cb2, 20, BW2, 88,
  "<b>㉖-4</b> 마무리 인사 · <b>발행 안 함</b><br>"
  "<span style='font-size:9px'>『오늘 하루도 화이팅하세요.<br>더 궁금한 게 있으면 다시 터치해 주세요』</span>",
  S_PROC + "fillColor=#EDF1F4;strokeColor=#4A6572;fontColor=#2B3B45;")
P("B27", cb1, 21, BW1, 60, "<b>㉗</b> <b>dialog.result</b> 스키마 검증 후 발행<br>QoS 1 · retain false", S_IO + CBIO)
P("B30", cb1, 22, BW1, 76,
  "<b>㉚</b> 에스코트 시작 멘트<br>"
  "<span style='font-size:9px'>『입고 도크로 직접 안내해 드릴게요.<br>안내견을 따라가세요』 — 동행은 C</span>", S_PROC + CB)
P("B31", cb1, 23, BW1, 88, "<b>㉛</b> B 세션 종료 → IDLE<br>"
  "<span style='font-size:9px'>상한 60초는 <b>조용할 때만</b> 흐른다 — 발화마다 되돌린다<br>"
  "상한 초과는 실패가 아니다(직원 호출 없음)</span>", S_TERM + CB)

# ============================================================ 3분류 묶음
#
# 담당자 요청 — **어느 단계가 한 덩어리인지 한눈에 보이게** 한다.
# 색을 칠하면 노드 자체 색(파랑=센서, 보라=LLM, 주황=에스코트)과 뒤섞이므로
# **점선 테두리만** 두른다. 채우지 않아서 그리는 순서(z-order)도 상관없다.
#
# 묶는 기준은 **본류(가운데 열)** 다. 곁가지(⑮ ⑰ ⑱ ⑲ …)는 자기를 부른 본류 노드가
# 속한 묶음에 속한다 — 곁가지까지 박스로 감싸면 박스끼리 겹쳐서 오히려 안 읽힌다.
#
# **3번 안에서 2번이 한 번 더 돈다** — ㉑ 확인 질의의 응답("네")도 녹음→STT→판정을
# 그대로 한 바퀴 탄다. 이게 빠지면 "확정인데 왜 3.8초냐" 를 도면으로 답할 수 없다.
# ---- 분류 밴드 -------------------------------------------------------------
# 점선 테두리만으로는 세 덩어리가 눈에 안 들어왔다(범위가 cb1 한 컬럼뿐이라 더 그랬다).
# **레인 전체 폭을 옅게 칠하고 왼쪽에 색 띠를 세운다** — 테두리보다 면이 먼저 읽힌다.
# 노드보다 아래에 깔려야 하므로 order 에서 레인 바로 뒤로 끌어올린다.
GX, GW = 612, 1276      # B 레인(600~1900) 안쪽

BANDS = {          # 선색          면색        칩 글씨색
    "#1E7F4F": ("#EEF8F2", "#FFFFFF"),
    "#2D6CDF": ("#EEF4FD", "#FFFFFF"),
    "#C98A00": ("#FFF9EE", "#FFFFFF"),
}


def group(nid, r0, r1, num, title, color):
    fill, chip_fg = BANDS[color]
    top = CY(r0) - 54
    h = CY(r1) + 54 - top
    N(nid, GX, top, GW, h, "",
      "rounded=1;arcSize=3;html=1;strokeWidth=1;fillColor=" + fill +
      ";strokeColor=" + color + ";opacity=60;", True)
    N(nid + "_s", GX, top, 9, h, "",        # 왼쪽 색 띠 — 면색이 옅어도 경계가 선다
      "rounded=0;html=1;strokeColor=none;fillColor=" + color + ";", True)
    N(nid + "_t", GX + GW - 278, top - 24, 260, 22,
      "<b>" + num + ". " + title + "</b>",
      "rounded=1;arcSize=40;html=1;strokeColor=none;fillColor=" + color +
      ";fontColor=" + chip_fg + ";fontSize=12;verticalAlign=middle;align=center;", True)
    # 면·띠는 노드 밑으로, 칩은 위로
    pos = order.index("lnB_h") + 1
    for x in (nid, nid + "_s"):
        order.remove(x)
        order.insert(pos, x)
        pos += 1


group("g1", 2, 7, "1", "세션 인계 · 안내 · PTT", "#1E7F4F")
group("g2", 8, 13, "2", "STT 인식", "#2D6CDF")
group("g3", 14, 23, "3", "목적지 확정 · C 인계", "#C98A00")

# 3 안에서 2가 한 번 더 도는 것 — 예전엔 ㉒ 바로 위에 놓아 **글자가 통째로 겹쳤다.**
# 배경 취급이라 겹침 검증에서 빠져 있었다(지금은 배경도 검사한다).
N("gnote", 1290, CY(16) - 34, 210, 68,
  "<span style='font-size:10px;color:#8A6A00'><b>3 안에서 2가 한 번 더 돈다</b><br>"
  "㉑ 의 응답(\"네\")도 녹음→STT→판정을<br>그대로 한 바퀴 탄다</span>",
  "rounded=1;arcSize=8;html=1;strokeWidth=1;dashed=1;dashPattern=4 3;"
  "fillColor=#FFFDF6;strokeColor=#D9B45B;align=left;verticalAlign=middle;"
  "spacingLeft=6;fontSize=10;", True)

# 연결자 (on-page connector)
N("ctA", LOOPX, CY(6) - 22, 44, 44, "A", S_CIRC + CCIRC_A)
N("csA3", cb2 + BW2 // 2 + 18, CY(20) - 22, 44, 44, "A", S_CIRC + CCIRC_A)
N("csA1", CORR3, CY(12) - 22, 44, 44, "A", S_CIRC + CCIRC_A)
N("csA2", 1858, CY(14) - 22, 44, 44, "A", S_CIRC + CCIRC_A)
N("ctB", CORR1, CY(13) + 40, 44, 44, "B", S_CIRC + CCIRC_B)
N("csB1", CORR1, CY(17) - 22, 44, 44, "B", S_CIRC + CCIRC_B)
N("csB2", cb4 - 22, CY(12) - 22, 44, 44, "B", S_CIRC + CCIRC_B)
N("csD2", CORR3, CY(15) - 22, 44, 44, "D", S_CIRC + CCIRC_D)
N("csD0", cb4 - 22, CY(8) - 22, 44, 44, "D", S_CIRC + CCIRC_D)
# L = 부재 확정 → ⑪ 이탈 판정 (여러 지점에서 발생하는 공통 예외를 한 곳으로 모은다)
N("csL1", 1180, 1400, 44, 44, "L", S_CIRC + CCIRC_L)   # 라벨이 앉을 가로 구간을 위해 옆으로
N("csL2", 1218, CY(14) + 48, 44, 44, "L", S_CIRC + CCIRC_L)
N("ctL", cb4 - 22, CY(9) - 22, 44, 44, "L", S_CIRC + CCIRC_L)

# 상시 감시 (병행) 그룹
N("mon", 1590, CY(3) + 30, 245, 300, "상시 감시 (병행 실행)",
  S_GROUP + "fillColor=#FFF9F8;strokeColor=#B3341C;fontColor=#B3341C;", True)
N("M1", 1605, CY(3) + 86, 215, 110,
  "① 오디오 링크 3초 무수신<br>② STT 연속 3회 실패<br>③ 세션 전체 60초 초과<br>"
  "<i>→ 하나라도 발생 시 ERROR</i>", S_PROC + CD)
N("M5", 1605, CY(4) + 60, 215, 76, "<b>system.health</b>(error) 발행<br>→ 에스컬레이션", S_PROC + CD)
N("M4", 1870, CY(11) - 50, 240, 100,
  "<b>MQTT 단절</b> → 로컬 큐 최대 10건 보관<br>재접속 시 재발행<br>"
  "<i>대화는 계속 진행 · 에스컬레이션 아님</i>", S_NOTE + "fillColor=#FFF9F8;strokeColor=#B3341C;fontColor=#5C1B10;")

# ============================================================ C 인터페이스 (외부 스텁 — 내부 프로세스는 최현수 도면)
# C — `work_docs/DogC_Flow_최신.md`(최현수, 09-14) 그대로.
# **PPT(09-07)는 구버전** — 카메라 추종을 걷어내기 전 설계라 참고하면 틀린다.
# AI 가 없다. 상태머신 + 거리센서 + 터치센서로만 돈다.
CC_BLE = "fillColor=#F4F4FB;strokeColor=#5B5BD6;fontColor=#22225C;dashed=1;dashPattern=6 4;"

P("C0", 2120, 19, C1W, 62,
  "<b>C-⓪</b> 대기 상태<br>"
  "<span style='font-size:9px'>목적지 안내 요청을 기다린다<br>(없으면 대기 유지)</span>",
  S_PRE + CC)
P("C1", 2120, 20, C1W, 74,
  "<b>C-①</b> <b>dialog.result</b> 수신 → 출발<br>"
  "<span style='font-size:9px'>목적지 ID → 웨이포인트 목록<br>"
  "노트북 ↔ 로봇은 <b>BLE</b> (MQTT 아님)</span>", S_PROC + CC)
P("C2", 2120, 21, C1W, 76,
  "<b>C-②</b> 웨이포인트 순차 이동<br>"
  "<span style='font-size:9px'><b>시간 기반</b> — 실측으로 산정한 초 단위<br>"
  "<i>위치를 모른다. 헛걸음해도 알 수 없다</i></span>", S_PROC + CC)
P("C3", 2120, 22, C1W, 88, "<b>C-③</b> 전방 장애물<br>15 cm 이내?", S_DEC + CC)
N("C4", 2300, CY(22) - 44, 250, 88,
  "<b>C-④</b> 회피 기동<br>"
  "<span style='font-size:9px'>후진→우회전→옆이동→좌회전 복귀→직진<br>"
  "<b>시도할수록 회피 반경이 넓어진다</b></span>", S_PROC + CC)
N("C5", 2300, CY(23) - 44, 250, 88, "<b>C-⑤</b> 회피 4회<br>실패?", S_DEC + CC)
N("C6", 2300, CY(24) - 31, 250, 62,
  "<b>C-⑥</b> 정지 + <b>alert.event</b><br>"
  "<span style='font-size:9px'>reason = <b>escort_lost</b></span>", S_IO + CD)
P("C7", 2120, 23, C1W, 88, "<b>C-⑦</b> 모든 웨이포인트<br>완료?", S_DEC + CC)
P("C8", 2120, 24, C1W, 76,
  "<b>C-⑧</b> 도착 → 인사 동작<br>"
  "<span style='font-size:9px'>action_run(<b>scrape_a_bow</b>)<br>"
  "<b>escort.status</b> 발행 (1 Hz · retain)</span>", S_IO + CC)
P("C9", 2120, 25, C1W, 88,
  "<b>C-⑨</b> 터치 감지?<br><i>최대 8초</i>", S_DEC + CC)
P("C10", 2120, 26, C1W, 66,
  "<b>C-⑩</b> 다음 안내 준비 완료<br>"
  "<span style='font-size:9px'>터치 즉시 / 8초 경과 자동<br><b>→ 대기 상태로 복귀</b></span>",
  S_PROC + CC)

# ============================================================ D 인터페이스 (외부 스텁 — 내부 프로세스는 백경률 도면)
N("ctD", 2813, CY(12) - 22, 44, 44, "D", S_CIRC + CCIRC_D)
# D 는 요약이다. 내부 상세는 백경률 코드(feature/security-dashboard).
# **A 옆에 고정 배치** — 호출받아 이동하지 않는다(이동·위치추정·회피 기능 제외).
P("D1", 2835, 2, DW, 76,
  "<b>D-①</b> <b>vision.face</b> · <b>vision.ppe</b> 수신<br>"
  "<span style='font-size:9px'>session_id 로 얼굴·PPE 결합<br>"
  "<b>AI 추론 없음</b> — A 의 판정을 받아 쓴다</span>", S_PROC + CD)
P("D2", 2835, 3, DW, 100,
  "<b>D-②</b> 상태 판정 <i>(우선순위)</i><br>"
  "<span style='font-size:9px'>unauthorized→<b>ALERT</b> · ppe fail→<b>WARNING</b><br>"
  "undetermined→PENDING · 그 외 NORMAL</span>", S_DEC + CD)
P("D3", 2835, 5, DW, 88,
  "<b>D-③</b> <b>alert.event</b> 발행<br>"
  "<span style='font-size:9px'>ALERT→critical · WARNING→warn<br>"
  "<b>상태가 바뀔 때만</b> · PENDING·NORMAL 은 발행 안 함</span>", S_IO + CD)
P("D4", 2835, 6, DW, 88,
  "<b>D-④</b> <b>robot.command</b>(warning_start)<br>"
  "<span style='font-size:9px'>2 legs stand + 부저 · 대시보드 표시<br>"
  "(session_id, reason) 별로 개별 관리</span>", S_IO + CD)
P("D5", 2835, 13, DW, 100,
  "<b>D-⑤</b> 관리자가<br>해제?<br>"
  "<span style='font-size:9px'><b>자동 해제 없음</b> — 재검사로 NORMAL 이 와도<br>"
  "물리 경고는 유지된다</span>", S_DEC + CD)
P("D7", 2835, 15, DW, 88,
  "<b>D-⑥</b> <b>resolved=true</b> + <b>warning_clear</b><br>"
  "<span style='font-size:9px'>D 활성 경고가 남아 있으면 자세 유지<br>"
  "B·C 경고만 해제 시 로봇은 그대로</span>", S_IO + CD)
N("D6", 2670, CY(15) + 60, DW, 140,
  "<b>경고 해제는 대시보드 수동 처리</b><br>재검사 통과 자동해제 <b>미지원</b> — "
  "alert.event가 세션 단위 <code>track_id</code>만 보유하고 세션을 잇는 "
  "영구 <code>visitor_id</code>가 미정 (09_작업기록 LOG-08)",
  S_NOTE + "fillColor=#FFF3F0;strokeColor=#B3341C;fontColor=#5C1B10;")

# ============================================================ 에지
E("V1", "A1", "게이트 도착", [(210, 170), (330, 170)], "dashed=1;")
E("A1", "A2", "", [(417, BOT("A1")), (417, TOP("A2"))])
E("A2", "A3", "", [(417, BOT("A2")), (417, TOP("A3"))])
E("A3", "A4", "신원", [(360, BOT("A3")), (330, ACY(2) + 40), (330, TOP("A4"))])
E("A3", "A7", "PPE", [(474, BOT("A3")), (504, ACY(2) + 40), (504, TOP("A7"))])
E("A4", "A5", "", [(330, BOT("A4")), (330, TOP("A5"))])
E("A5", "A6", "", [(330, BOT("A5")), (330, TOP("A6"))])
E("A7", "A8", "", [(504, BOT("A7")), (504, TOP("A8"))])
E("A8", "A9", "", [(504, BOT("A8")), (504, TOP("A9"))])
E("A6", "A10", "", [(330, BOT("A6")), (330, ACY(5) + 44), (390, ACY(5) + 44), (390, TOP("A10"))])
E("A9", "A10", "", [(504, BOT("A9")), (504, ACY(5) + 44), (444, ACY(5) + 44), (444, TOP("A10"))])
E("A10", "A11", "", [(417, BOT("A10")), (417, TOP("A11"))])
E("A11", "A12", "미통과", [(417, BOT("A11")), (417, TOP("A12"))])
E("A11", "B01", "gate.session",
  [(584, MID("A11")), (606, MID("A11")), (606, MID("B01")), (680, MID("B01"))])
E("A3", "D1", "vision.face · vision.ppe",
  [(584, MID("A3")), (598, MID("A3")), (598, 146), (2835, 146), (2835, TOP("D1"))],
  "dashed=1;")
E("D1", "D2", "", [(2835, BOT("D1")), (2835, TOP("D2"))])
E("D2", "D3", "WARNING · ALERT", [(2835, BOT("D2")), (2835, TOP("D3"))])
E("D3", "D4", "", [(2835, BOT("D3")), (2835, TOP("D4"))])
E("D4", "D5", "", [(3000, MID("D4")), (3040, MID("D4")), (3040, MID("D5")), (3000, MID("D5"))])
E("D5", "D7", "해제", [(2835, BOT("D5")), (2835, TOP("D7"))])
E("B01", "B06", "", [(790, BOT("B01")), (790, TOP("B06"))])
E("B06", "B06b", "", [(CXX("B06"), BOT("B06")), (CXX("B06b"), TOP("B06b"))])
E("B06b", "B06c", "", [(CXX("B06b"), BOT("B06b")), (CXX("B06c"), TOP("B06c"))])
E("B06c", "B07", "네 — 터치 감지", [(CXX("B06c"), BOT("B06c")), (CXX("B07"), TOP("B07"))])
E("B06c", "B08b", "아니요 — 15초 무터치", [(RGT("B06c"), MID("B06c")), (1090, CY(7)), (CXX("B08b"), TOP("B08b"))])
E("ctA", "B06b", "터치부터 다시", [(RGT("ctA"), MID("ctA")), (LFT("B06b"), MID("B06b"))])
E("B07", "B08", "", [(CXX("B07"), BOT("B07")), (CXX("B08"), TOP("B08"))])
E("V2", "B08", "발화 입력 (USB 마이크 · RPi5)",
  [(RGT("V2"), MID("V2")), (224, CY(9)), (224, CY(11) + 60), (662, CY(11) + 60), (662, CY(9)), (LFT("B08"), MID("B08"))],
  "dashed=1;")
E("B08", "B08b", "No (7초 무발화)", [(RGT("B08"), MID("B08")), (LFT("B08b"), MID("B08b"))])
E("B08b", "B09", "네 — 앞에 있음", [(RGT("B08b"), MID("B08b")), (LFT("B09"), MID("B09"))])
E("B08b", "csL1", "아니요 — 없음 확정", [(CXX("B08b"), BOT("B08b")), (1090, CY(10) - 48), (LFT("csL1"), MID("csL1"))])
E("ctL", "B11", "", [(CXX("ctL"), BOT("ctL")), (CXX("B11"), TOP("B11"))])
E("B09", "B10", "", [(CXX("B09"), BOT("B09")), (CXX("B10"), TOP("B10"))])
E("B08", "B12", "Yes", [(CXX("B08"), BOT("B08")), (CXX("B12"), TOP("B12"))])
E("B10", "B12", "Yes", [(LFT("B10"), MID("B10")), (RGT("B12"), MID("B12"))])
E("B10", "B11", "No", [(RGT("B10"), MID("B10")), (LFT("B11"), MID("B11"))])
E("B11", "EX2", "", [(RGT("B11"), MID("B11")), (LFT("EX2"), MID("EX2"))])
E("B12", "B13", "", [(CXX("B12"), BOT("B12")), (CXX("B13"), TOP("B13"))])
E("B13", "B14", "", [(CXX("B13"), BOT("B13")), (CXX("B14"), TOP("B14"))])
E("B14", "B15", "Yes (2개 이상)", [(RGT("B14"), MID("B14")), (LFT("B15"), MID("B15"))])
E("B15", "B15b", "", [(RGT("B15"), MID("B15")), (LFT("B15b"), MID("B15b"))])
E("B15b", "csA1", "No", [(RGT("B15b"), MID("B15b")), (LFT("csA1"), MID("csA1"))])
E("B15b", "csB2", "Yes → 시도 횟수로 합산", [(CXX("B15b"), BOT("B15b")), (1390, CY(13) - 60), (1700, CY(13) - 60), (CXX("csB2"), BOT("csB2"))])
E("B14", "B14b", "No — 후보 0개", [(790, CY(12) + 50), (790, CY(13) - 38)])
E("B14b", "B16", "목적지 나옴", [(790, CY(13) + 38), (790, CY(14) - 50)])
E("B14b", "ctB", "null / 실패 → 재질문", [(900, CY(13)), (940, CY(13)), (940, CY(13) + 40)])
E("B14", "B16", "No — 후보 1개", [(680, CY(12)), (650, CY(12)), (650, CY(14)), (680, CY(14))])
E("B16", "B17", "No", [(900, CY(14)), (980, CY(14))])
E("ctB", "B17", "", [(962, CY(13) + 62), (1090, CY(13) + 62), (1090, CY(14) - 50)])
E("B17", "B17b", "Yes", [(1200, CY(14)), (1280, CY(14))])
E("B17b", "B18", "네 — 앞에 있음", [(1500, CY(14)), (1580, CY(14))])
E("B17b", "csL2", "아니요", [(1335, CY(14) + 50), (1335, CY(14) + 70), (1262, CY(14) + 70)])
E("B18", "csA2", "", [(1820, CY(14)), (1858, CY(14))])
E("B17", "B19", "No (3회 도달)", [(1090, CY(14) + 50), (1090, CY(15)), (1280, CY(15))])
E("B19", "csD2", "", [(1500, CY(15)), (1518, CY(15))])
E("B16", "B20", "Yes", [(790, CY(14) + 50), (790, CY(15) - 50)])
E("B20", "B21", "Yes ≥ 0.75", [(790, CY(15) + 50), (790, CY(16) - 38)])
E("B20", "B22", "No (0.45~0.75)", [(900, CY(15)), (940, CY(15)), (940, CY(16)), (980, CY(16))])
E("B21", "B23", "", [(790, CY(16) + 38), (790, CY(17) - 50)])
E("B22", "B23", "", [(1090, CY(16) + 38), (1090, CY(16) + 60), (850, CY(16) + 60), (850, CY(17) - 50)])
E("V3", "B23", "응답 입력", [(210, CY(17)), (680, CY(17))], "dashed=1;")
E("B23", "csB1", "부정 · 사양 → 재질문", [(900, CY(17)), (918, CY(17))])
E("B23", "B26", "긍정", [(790, CY(17) + 50), (790, CY(18) - 32)])
E("B26", "B26b", "", [(790, CY(18) + 32), (790, CY(19) - 44)])
E("B26b", "B26c", "", [(790, CY(19) + 44), (790, CY(20) - 50)])
E("B26c", "B26d", "사양 / 무응답", [(900, CY(20)), (980, CY(20))])
E("B26d", "csA3", "터치 대기로 복귀", [(1200, CY(20)), (1218, CY(20))])
E("B26c", "B27", "수락", [(790, CY(20) + 50), (790, CY(21) - 30)])
E("B27", "C0", "dialog.result (QoS 1)",
  [(900, CY(21)), (1820, CY(21)), (1820, TOP("C0") - 30), (2120, TOP("C0") - 30),
   (2120, TOP("C0"))])
E("C0", "C1", "요청 수신", [(2120, BOT("C0")), (2120, TOP("C1"))])
E("C1", "C2", "", [(2120, BOT("C1")), (2120, TOP("C2"))])
E("C2", "C3", "", [(2120, BOT("C2")), (2120, TOP("C3"))])
E("C3", "C7", "No — 장애물 없음", [(2120, BOT("C3")), (2120, TOP("C7"))])
E("C7", "C8", "Yes", [(2120, BOT("C7")), (2120, TOP("C8"))])
# ⑦ No — 웨이포인트가 남았으면 ② 로 돌아간다. 이 분기가 없으면 도면상 순회가 끝나지
# 않는다(실제 코드에는 있는데 도면에만 빠져 있었다). 레인 왼쪽 여백을 코리도로 쓴다.
# 라벨은 경로 중간(= ③ 옆)에 앉으면 ③ 을 덮는다. ② 와 ③ 사이 빈 띠로 올린다.
_c7y, _c2y = MID("C7"), MID("C2")
_mid_y = _c7y - ((28 + (_c7y - _c2y)) / 2 - 14)
E("C7", "C2", "No — 다음 웨이포인트",
  [(LFT("C7"), MID("C7")), (LFT("C7") - 14, MID("C7")),
   (LFT("C7") - 14, MID("C2")), (LFT("C2"), MID("C2"))],
  loff=(88, (BOT("C2") + TOP("C3")) / 2 - _mid_y))
E("C8", "C9", "", [(2120, BOT("C8")), (2120, TOP("C9"))])
E("C9", "C10", "터치 or 8초", [(2120, BOT("C9")), (2120, TOP("C10"))])

# 회피는 **본류에서 오른쪽으로 나갔다가 돌아온다** — 예외 처리를 세로로 늘어놓으면
# 주 흐름이 어디인지 눈으로 못 따라간다.
E("C3", "C4", "Yes", [(RGT("C3"), MID("C3")), (LFT("C4"), MID("C4"))])
E("C4", "C5", "", [(CXX("C4"), BOT("C4")), (CXX("C5"), TOP("C5"))])
E("C5", "C6", "Yes", [(CXX("C5"), BOT("C5")), (CXX("C6"), TOP("C6"))])
E("C5", "C7", "No — 경로 복귀",
  [(LFT("C5"), MID("C5")), (2244, MID("C5")), (2244, MID("C7")), (RGT("C7"), MID("C7"))])
E("C10", "C0", "다음 손님",
  [(LFT("C10"), MID("C10")), (1912, MID("C10")), (1912, MID("C0")), (LFT("C0"), MID("C0"))])
E("B27", "B30", "", [(790, CY(21) + 30), (790, CY(22) - 38)])
E("B30", "B31", "", [(790, CY(22) + 38), (790, CY(23) - 25)])
E("M1", "M5", "", [(CXX("M1"), BOT("M1")), (CXX("M5"), TOP("M5"))])
E("M5", "csD0", "", [(CXX("M5"), BOT("M5")), (1712, TOP("csD0"))])
E("ctD", "D5", "B·C 경고도 같은 토픽으로", [(2835, CY(12) + 22), (2835, TOP("D5"))])
E("D7", "D6", "", [(2835, BOT("D7")), (2835, TOP("D6"))], "dashed=1;endArrow=none;")

# ============================================================ 범례
#
# 예전에는 여기에 **정보 패널 19개**(신뢰도표·시간제한·BR 15개·멘트 목록 …)와
# **데이터 계층 밴드**(2-호스트 HW 구성)가 붙어 있었다. 전부 걷어냈다 —
# 도면 옆에 설명을 줄줄이 붙여야 읽히는 건 차트가 아니다.
# **차트만 보고 알 수 있어야 하므로, 그 내용은 노드 라벨 안으로 들어가야 한다.**
# (표로 봐야 하는 것들은 04_B_비즈니스_Flow.md 에 그대로 있다.)
#
# 남기는 것은 도형 규칙 하나뿐이다. 이건 설명이 아니라 **읽는 법**이라 도면에 있어야 한다.
PC1, PWD = 2580, 520


def panel(nid, col, y, h, title, body, color="fillColor=#FBFCFD;strokeColor=#8FA0B3;fontColor=#26384F;"):
    lab = ("<div style='background:#26384F;color:#fff;margin:-6px -6px 6px -8px;"
           "padding:4px 8px;font-size:12px;font-weight:bold'>" + title + "</div>" + body)
    N(nid, col, y, PWD, h, lab, S_PANEL + color, True)


panel("pLeg", PC1, 140, 250, "범례 — 도형 규칙 (KS X ISO 5807 기준)",
      "<table style='font-size:10px' cellpadding='2'>"
      "<tr><td><b>둥근 사각</b></td><td>시작 / 종료</td></tr>"
      "<tr><td><b>사각</b></td><td>처리</td></tr>"
      "<tr><td><b>마름모</b></td><td>판단 — 분기마다 조건 라벨</td></tr>"
      "<tr><td><b>평행사변형</b></td><td>MQTT 메시지 발행</td></tr>"
      "<tr><td><b>겹사각</b></td><td>대기 (청취)</td></tr>"
      "<tr><td><b>원 A/B/D/L</b></td><td>되돌아가는 흐름 (긴 화살표 대신 연결자로 — 교차 제거)<br>"
      "<b>A</b> 터치 대기 복귀 · <b>B</b> 시도횟수 검사 · <b>D</b> 에스컬레이션 · <b>L</b> 이탈 판정</td></tr>"
      "<tr><td><b>점선</b></td><td>사람의 물리 행동 · 병행 감시</td></tr>"
      "<tr><td><b>파란 도형</b></td><td>터치·초음파 센서로 판단하는 단계</td></tr></table>")


# ============================================================ B 레인 오른쪽 늘리기
# ⑪ 옆 종료 노드와 MQTT 단절 주석이 B 레인 폭(1300)을 240px 넘어 **C 레인 배경 위에**
# 올라가 있었다. 좌표를 하나씩 손대면 또 어긋나므로, 경계 오른쪽(x>=1940)을 통째로 민다.
BSPLIT, BSHIFT = 1940, 250
for _v in nodes.values():
    if _v['x'] >= BSPLIT:
        _v['x'] += BSHIFT
nodes['lnB_b']['w'] += BSHIFT
for _e in edges:
    _e['pts'] = [(x + BSHIFT if x >= BSPLIT else x, y) for x, y in _e['pts']]

# 범례는 레인 위에 얹으면 안 된다 — 맨 오른쪽 레인 바깥으로 뺀다.
_right = max(nodes[lid + "_b"]['x'] + nodes[lid + "_b"]['w'] for lid, *_ in LANES)
nodes['pLeg']['x'] = _right + 40

# ============================================================ 레인 높이 맞추기
# 레인은 노드보다 **먼저** 만들어져서 도면이 얼마나 길어질지 모른다. 고정값으로 두면
# 행 간격을 넓힐 때마다 노드가 배경 밖으로 삐져나간다(실제로 C 가 643px 넘친 적이 있다).
# 다 만든 뒤에 가장 아래 노드에 맞춰 늘린다.
_bottom = max(v['y'] + v['h'] for k, v in nodes.items() if k not in bg)
for _lid, *_ in LANES:
    nodes[_lid + "_b"]['h'] = _bottom + 60 - BODY_Y

# ============================================================ 검증
def rects():
    return [(k, v) for k, v in nodes.items() if k not in bg]


def overlap(a, b, m=6):
    return (a['x'] < b['x'] + b['w'] + m and b['x'] < a['x'] + a['w'] + m and
            a['y'] < b['y'] + b['h'] + m and b['y'] < a['y'] + a['h'] + m)


# 도면 위에 얹는 주석(노트·범례·칩)은 **배경이라 겹침 검사에서 빠져 있었다** —
# 그래서 gnote 가 ㉒ 를 통째로 덮은 걸 아무도 못 잡았다. 레인과 밴드만 면제한다.
# 레인은 노드를 덮는 게 정상이라 면제한다. 주석·칩은 덮으면 안 되므로 검사 대상이다.
LAYERS = ({"title", "mon", "g1", "g2", "g3", "g1_s", "g2_s", "g3_s"}
          | {lid + suffix for lid, *_ in LANES for suffix in ("_b", "_h")})
OVERLAYS = [(k, nodes[k]) for k in nodes if k in bg and k not in LAYERS]


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

for k, v in OVERLAYS:
    for k2, v2 in rs:
        if overlap(v, v2, m=0):
            errs.append("OVERLAY: %s covers %s" % (k, k2))

for i in range(len(OVERLAYS)):
    for j in range(i + 1, len(OVERLAYS)):
        if overlap(OVERLAYS[i][1], OVERLAYS[j][1], m=0):
            errs.append("OVERLAY: %s x %s" % (OVERLAYS[i][0], OVERLAYS[j][0]))

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
errs += errs_pre


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


def seg_hits(p, q, r, m=3):
    x1, y1 = p
    x2, y2 = q
    lo_x, hi_x = min(x1, x2) - m, max(x1, x2) + m
    lo_y, hi_y = min(y1, y2) - m, max(y1, y2) + m
    return (lo_x < r['x'] + r['w'] and r['x'] < hi_x and
            lo_y < r['y'] + r['h'] and r['y'] < hi_y)


for e in edges:
    for k, v in rs:
        if k in (e['s'], e['d']):
            continue
        for i in range(len(e['pts']) - 1):
            if seg_hits(e['pts'][i], e['pts'][i + 1], v):
                errs.append("EDGE %s->%s seg%d hits %s" % (e['s'], e['d'], i, k))

# 에지 폴리라인이 실제로 소스/타깃 경계에서 시작·끝나는지
for e in edges:
    for nid, pt in ((e['s'], e['pts'][0]), (e['d'], e['pts'][-1])):
        n = nodes[nid]
        px, py = pt
        if not (n['x'] - 4 <= px <= n['x'] + n['w'] + 4 and n['y'] - 4 <= py <= n['y'] + n['h'] + 4):
            errs.append("ANCHOR %s->%s: point (%s,%s) not on %s boundary" %
                        (e['s'], e['d'], px, py, nid))

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

# ============================================================ XML 출력
def frac(n, pt):
    return ((pt[0] - n['x']) / n['w'], (pt[1] - n['y']) / n['h'])


# **페이지를 도면 크기에 맞춘다.** 고정값으로 두면 도면이 커졌을 때 PDF 로 뽑을 때
# 오른쪽·아래가 잘린다(3480 인데 도면이 4050 까지 간 적이 있다).
PAGE_W = int(max(n['x'] + n['w'] for n in nodes.values()) + 80)
PAGE_H = int(max(n['y'] + n['h'] for n in nodes.values()) + 80)

out = ['<mxfile host="app.diagrams.net" version="24.7.17">',
       '  <diagram name="팀 통합 Flow (A·B·C·D)" id="team-flow">',
       '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" '
       'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
       'pageWidth="%d" pageHeight="%d" math="0" shadow="0">' % (PAGE_W, PAGE_H),
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

DST = r"D:\Downloads\Mechdog\work_docs\exports\통합_비즈니스_Flow.drawio"
open(DST, "w", encoding="utf-8").write("\n".join(out))
print("저장:", DST)
