# -*- coding: utf-8 -*-
"""MechDog B 비즈니스 Flow — .drawio 생성 + 겹침/교차 자동 검증.

    python tools/gen_b_flowchart.py

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

CY = lambda k: 170 + 130 * k

# ---- 컬럼 좌표 --------------------------------------------------------------
VX, VW = 60, 200        # 방문자        cx 160
AX, AW = 340, 220       # A 게이트      cx 450
B1, B2, B3, B4 = 680, 980, 1280, 1580
BW1 = BW2 = BW3 = 220
BW4 = 240
C1X, C1W = 1960, 220    # C            cx 2070
DX, DW = 2260, 240      # D            cx 2380
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


edges = []      # (src, dst, label, style, [절대 폴리라인 점들])


def E(s, d, label, pts, style="", loff=None):
    """loff 는 라벨을 경로 중간에서 밀어내는 (dx, dy). 라벨이 무관한 노드를 덮을 때만 쓴다."""
    edges.append(dict(s=s, d=d, label=label, pts=[(float(a), float(b)) for a, b in pts],
                      style=style, loff=loff))


# ============================================================ 제목 / 레인
TITLE = ("<b style=\"font-size:22px\">MechDog B 비즈니스 Flow — 전체 통합 Flowchart</b>"
         "&nbsp;&nbsp;<span style=\"font-size:12px;color:#5A6B7D\">"
         "MD-BF-B-001 <b>v3.0</b> · 2026-09-18 · 김별이 &nbsp;|&nbsp; "
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
BODY_Y, BODY_H = 130, 3200        # 130 .. 3190
LANES = [
    ("lnV", VX - 20, 240, "방문자", "fillColor=#C98A00;", "fillColor=#FFFDF7;strokeColor=#E0CB9B;"),
    ("lnB", 600, 1300, "MechDog B · 대화 (본 문서 대상)", "fillColor=#1E7F4F;", "fillColor=#FAFEFB;strokeColor=#B4D8C4;"),
]
for lid, lx, lw, lname, hstyle, bstyle in LANES:
    N(lid + "_b", lx, BODY_Y, lw, BODY_H, "", "rounded=0;html=1;strokeWidth=1.5;" + bstyle, True)
    N(lid + "_h", lx, LANE_Y, lw, LANE_H, "<b>" + lname + "</b>",
      "rounded=0;html=1;strokeWidth=1.5;fontColor=#FFFFFF;fontSize=14;verticalAlign=middle;align=center;strokeColor=none;" + hstyle, True)

# ============================================================ 방문자 (B와 직접 접하는 구간만)
P("V1", 160, 0, VW, 50, "방문자 게이트 도착", S_TERM + CV)
P("V2", 160, 9, VW, 64, "방문 목적 발화<br><i>\"입고요\" / \"도크 갈게요\"</i>", S_PROC + CV)
P("V3", 160, 17, VW, 64, "확인 질의에 응답<br><i>긍정 7종 / 부정 5종 / 무응답</i>", S_PROC + CV)

# ============================================================ A 인터페이스 (외부 스텁 — 내부 프로세스는 여도훈 도면)
P("EXT_A", 450, 2, AW, 70,
  "🔗 <b>A · 게이트 (외부)</b><br><i>얼굴 인가 + PPE 판정</i><br>"
  "<b>gate.session</b> 발행 → 여기로<br><span style='font-size:8px'>여도훈 도면과 병합 예정</span>",
  S_EXT)

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
# ㉖-1 — 제안 멘트(㉖-2)에 "직접 안내해 드릴까요" 가 **같은 문장으로** 들어 있어서
# 이 판단은 반드시 그 **앞**에 와야 한다. 물어본 뒤에 못 한다고 하면 더 나쁘다. (FR-B-708)
P("B26a", cb2, 18, BW2, 100,
  "<b>㉖-1</b> 안내견이<br>대기 중인가?<br><span style='font-size:9px'>escort.status = <b>idle</b></span>", S_DEC + 'fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5C3F00;')
P("B26e", cb3, 18, BW3, 88,
  "<b>㉖-1b</b> 혼잡 안내 + <b>위치만</b><br><span style='font-size:9px'>『모든 안내견이 안내 중이에요』<br><b>가안 — 멘트 신규 · TTS 필요</b></span>", S_PROC + 'fillColor=#FFF6E5;strokeColor=#C98A00;fontColor=#5C3F00;')
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
N("ctA", LOOPX + 15, CY(6) - 22, 44, 44, "A", S_CIRC + CCIRC_A)
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
N("mon", 1590, 620, 245, 300, "상시 감시 (병행 실행)",
  S_GROUP + "fillColor=#FFF9F8;strokeColor=#B3341C;fontColor=#B3341C;", True)
N("M1", 1605, CY(3) + 86, 215, 132,
  "<b>미처리 예외</b> — 대화 루프가 통째로 죽을 때<br><span style='font-size:9px'>세션 60초는 <b>조용할 때만</b> 흐른다 (발화마다 초기화)<br>초과해도 <b>leave() 로 조용히 닫는다 — 에스컬레이션 아님</b><br>오디오 단절·STT 연속 실패 감시는 <b>미구현</b></span>", S_PROC + CD)
N("M5", 1605, CY(4) + 100, 215, 76,
  "<b>system.health(error)</b> 발행 후 종료<br><span style='font-size:9px'>대시보드에 이유만 남긴다 · <b>직원 호출 없음</b></span>", S_PROC + CD)
N("M4", 1870, CY(11) - 50, 240, 100,
  "<b>MQTT 단절</b> → 로컬 큐 최대 10건 보관<br>재접속 시 재발행<br>"
  "<i>대화는 계속 진행 · 에스컬레이션 아님</i>", S_NOTE + "fillColor=#FFF9F8;strokeColor=#B3341C;fontColor=#5C1B10;")

# ============================================================ C 인터페이스 (외부 스텁 — 내부 프로세스는 최현수 도면)
P("EXT_C", 2070, 20, C1W, 70,
  "🔗 <b>C · 에스코트 (외부)</b><br><i>경로 계획 → 동행 → 도착</i><br>"
  "<b>dialog.result</b> 여기서 수신<br><span style='font-size:8px'>최현수 도면과 병합 예정</span>",
  S_EXT)

# ============================================================ D 인터페이스 (외부 스텁 — 내부 프로세스는 백경률 도면)
N("ctD", 2358, CY(12) - 22, 44, 44, "D", S_CIRC + CCIRC_D)
P("EXT_D", 2380, 13, DW, 70,
  "🔗 <b>D · 보안/예외 대응 (외부)</b><br><i>대시보드 경고 · 직원 호출 · 수동 안내</i><br>"
  "<b>alert.event</b> 여기서 수신<br><span style='font-size:8px'>백경률 도면과 병합 예정</span>",
  S_EXT)
N("D6", 2260, 1940, DW, 140,
  "<b>경고 해제는 대시보드 수동 처리</b><br>재검사 통과 자동해제 <b>미지원</b> — "
  "alert.event가 세션 단위 <code>track_id</code>만 보유하고 세션을 잇는 "
  "영구 <code>visitor_id</code>가 미정 (09_작업기록 LOG-08)",
  S_NOTE + "fillColor=#FFF3F0;strokeColor=#B3341C;fontColor=#5C1B10;")

# ============================================================ 에지
E("V1", "EXT_A", "게이트 도착", [(260, 170), (450, 170), (450, 395)], "dashed=1;")
E("EXT_A", "B01", "gate.session 발행", [(560, 430), (680, 430)])
E("B01", "B06", "", [(790, 455), (790, 788)])
E("B06", "B06b", "", [(790, 852), (790, 918)])
E("B06b", "B06c", "", [(790, 982), (790, 1030)])
E("B06c", "B07", "네 — 터치 감지", [(790, 1130), (790, 1166)])
E("B06c", "B08b", "아니요 — 15초 무터치", [(900, 1080), (1090, 1080), (1090, 1290)])
E("ctA", "B06b", "", [(672, 950), (680, 950)])
E("B07", "B08", "", [(790, 1242), (790, 1290)])
E("V2", "B08", "발화 입력 (USB 마이크 · RPi5)", [(260, 1340), (680, 1340)], "dashed=1;")
E("B08", "B08b", "No (7초 무발화)", [(900, 1340), (980, 1340)])
E("B08b", "B09", "네 — 앞에 있음", [(1200, 1340), (1280, 1340)])
E("B08b", "csL1", "아니요 — 없음 확정", [(1090, 1390), (1090, 1422), (1180, 1422)])
E("ctL", "B11", "", [(1700, 1362), (1700, 1438)])
E("B09", "B10", "", [(1390, 1372), (1390, 1420)])
E("B08", "B12", "Yes", [(790, 1390), (790, 1438)])
E("B10", "B12", "Yes", [(1280, 1470), (900, 1470)])
E("B10", "B11", "No", [(1500, 1470), (1580, 1470)])
E("B11", "EX2", "", [(1820, 1470), (1870, 1470)])
E("B12", "B13", "", [(790, 1502), (790, 1568)])
E("B13", "B14", "", [(790, 1632), (790, 1680)])
E("B14", "B15", "Yes (2개 이상)", [(900, 1730), (980, 1730)])
E("B15", "B15b", "", [(1200, 1730), (1280, 1730)])
E("B15b", "csA1", "No", [(1500, 1730), (1518, 1730)])
E("B15b", "csB2", "Yes → 시도 횟수로 합산", [(1390, 1780), (1390, 1800), (1700, 1800), (1700, 1752)])
E("B14", "B14b", "No — 후보 0개", [(790, CY(12) + 50), (790, CY(13) - 38)])
E("B14b", "B16", "목적지 나옴", [(790, CY(13) + 38), (790, CY(14) - 50)])
E("B14b", "ctB", "null / 실패 → 재질문", [(900, CY(13)), (940, CY(13)), (940, CY(13) + 40)],
  loff=(32, -13))
E("B14", "B16", "No — 후보 1개", [(680, CY(12)), (650, CY(12)), (650, CY(14)), (680, CY(14))],
  loff=(45, 59))
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
E("V3", "B23", "응답 입력", [(260, CY(17)), (680, CY(17))], "dashed=1;")
E("B23", "csB1", "부정 · 사양 → 재질문", [(900, CY(17)), (918, CY(17))], loff=(110, 0))
E("B23", "B26", "긍정", [(790, CY(17) + 50), (790, CY(18) - 32)])
E("B26", "B26a", "", [(900, CY(18)), (980, CY(18))])
E("B26a", "B26b", "대기 중",
  [(1090, CY(18) + 50), (1090, CY(19)), (900, CY(19))])
E("B26a", "B26e", "이동·복귀 중", [(1200, CY(18)), (1280, CY(18))])
E("B26e", "B26d", "",
  [(1390, CY(18) + 44), (1390, CY(20) - 70), (1090, CY(20) - 70), (1090, CY(20) - 44)])
E("B26b", "B26c", "", [(790, CY(19) + 44), (790, CY(20) - 50)])
E("B26c", "B26d", "사양 / 무응답", [(900, CY(20)), (980, CY(20))])
E("B26d", "csA3", "터치 대기로 복귀", [(1200, CY(20)), (1218, CY(20))], loff=(110, 0))
E("B26c", "B27", "수락", [(790, CY(20) + 50), (790, CY(21) - 30)])
E("B27", "EXT_C", "dialog.result (QoS 1)", [(900, CY(21)), (2070, CY(21)), (2070, 2738)])
E("B27", "B30", "", [(790, CY(21) + 30), (790, CY(22) - 38)])
E("B30", "B31", "", [(790, CY(22) + 38), (790, CY(23) - 25)])
E("M1", "M5", "", [(1712, 778), (1712, 790)])
E("M5", "csD0", "", [(1712, 866), (1712, 1188)])
E("ctD", "EXT_D", "", [(2380, CY(12) + 22), (2380, CY(13) - 35)])
E("EXT_D", "D6", "", [(2380, 1898), (2380, 1940)], "dashed=1;endArrow=none;")

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


# ============================================================ 검증
def rects():
    return [(k, v) for k, v in nodes.items() if k not in bg]


def overlap(a, b, m=6):
    return (a['x'] < b['x'] + b['w'] + m and b['x'] < a['x'] + a['w'] + m and
            a['y'] < b['y'] + b['h'] + m and b['y'] < a['y'] + a['h'] + m)


# 도면 위에 얹는 주석(노트·범례·칩)은 **배경이라 겹침 검사에서 빠져 있었다** —
# 그래서 gnote 가 ㉒ 를 통째로 덮은 걸 아무도 못 잡았다. 레인과 밴드만 면제한다.
LAYERS = {"title", "lnV_b", "lnV_h", "lnB_b", "lnB_h", "mon",
          "g1", "g2", "g3", "g1_s", "g2_s", "g3_s"}
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
       '  <diagram name="B 비즈니스 Flow (전체)" id="bflow-all">',
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

DST = r"D:\Downloads\Mechdog\work_docs\exports\B_비즈니스_Flow.drawio"
open(DST, "w", encoding="utf-8").write("\n".join(out))
print("저장:", DST)
