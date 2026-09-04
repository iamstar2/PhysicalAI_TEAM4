// MechDog 보안 관제 대시보드 - 프런트엔드
// 실시간 갱신 방식: 1초 간격 폴링 (fetch로 /api/state 반복 조회).
// WebSocket/SSE보다 구현이 훨씬 단순하고, 이 화면 용도(사람이 보는 관제 화면)에는
// 1초 지연이 체감상 문제되지 않아서 선택했다. 자세한 이유는 README.md 참고.

const POLL_INTERVAL_MS = 1000;

const NODE_STATE_LABEL = {
  ready: "정상",
  booting: "부팅중",
  busy: "작동중",
  error: "오류",
  offline: "오프라인",
  UNKNOWN: "알 수 없음",
};

const FACE_LABEL = {
  authorized: "인가됨",
  unauthorized: "미인가",
  undetermined: "판정 불가",
};

const PPE_LABEL = {
  pass: "착용",
  fail: "미착용",
  undetermined: "판정 불가",
};

const STATUS_LABEL = {
  NORMAL: "정상",
  PENDING: "판정 대기",
  WARNING: "안전복장 문제",
  ALERT: "미인가 인물",
};

const REASON_LABEL = {
  unauthorized: "미인가 인물",
  no_helmet: "안전모 미착용",
  no_vest: "안전조끼 미착용",
  face_timeout: "얼굴 판정 시간초과",
  escort_lost: "에스코트 이탈",
};

const LEVEL_LABEL = { info: "정보", warn: "경고", critical: "위험" };

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function renderNodes(nodes) {
  for (const node of ["mechdog_a", "mechdog_b", "mechdog_c", "mechdog_d"]) {
    const info = nodes[node] || { state: "UNKNOWN", ts: null };
    const stateEl = document.getElementById(`state-${node}`);
    const tsEl = document.getElementById(`ts-${node}`);
    const stateKey = info.state === "UNKNOWN" ? "unknown" : info.state;
    stateEl.textContent = NODE_STATE_LABEL[info.state] || info.state;
    stateEl.className = `node-state ${stateKey}`;
    tsEl.textContent = info.ts ? `마지막 수신: ${info.ts}` : "수신된 적 없음";
  }
}

function renderMqtt(connected) {
  const dot = document.getElementById("mqttDot");
  const text = document.getElementById("mqttText");
  dot.className = "dot " + (connected ? "on" : "off");
  text.textContent = connected ? "MQTT 연결됨" : "MQTT 연결 끊김";
}

function renderVisitor(visitor) {
  const el = document.getElementById("visitorInfo");
  el.innerHTML = "";
  if (!visitor) {
    el.textContent = "방문자 정보 없음";
    return;
  }
  const rows = [
    ["세션 ID", visitor.session_id],
    ["방문자 ID", visitor.visitor_id || "-"],
    ["얼굴 판정", FACE_LABEL[visitor.face_result] || "대기중"],
    ["안전모", PPE_LABEL[visitor.ppe.helmet] || "대기중"],
    ["안전조끼", PPE_LABEL[visitor.ppe.vest] || "대기중"],
    ["PPE 종합", PPE_LABEL[visitor.ppe.overall] || "대기중"],
  ];
  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "row";
    const l = document.createElement("span");
    l.className = "label";
    l.textContent = label;
    const v = document.createElement("span");
    v.textContent = value;
    row.appendChild(l);
    row.appendChild(v);
    el.appendChild(row);
  }
}

function renderStatus(visitor) {
  const el = document.getElementById("statusBadge");
  if (!visitor) {
    el.textContent = "데이터 없음";
    el.className = "status-badge status-unknown";
    return;
  }
  const status = visitor.status;
  if (!status) {
    // 관리자가 방금 경고를 해제해서 status가 초기화된 상태 - 데이터가 없는 게 아니라
    // "해제되어 다음 판정을 기다리는" 상태라서 PENDING과 같은 스타일로 보여준다.
    el.textContent = "판정 대기 (해제됨)";
    el.className = "status-badge status-pending";
    return;
  }
  el.textContent = `${STATUS_LABEL[status] || status} (${status})`;
  el.className = "status-badge status-" + status.toLowerCase();
}

function renderActiveAlert(alert) {
  const el = document.getElementById("activeAlert");
  const clearBtn = document.getElementById("clearAlertBtn");

  if (!alert) {
    el.className = "active-alert";
    el.textContent = "현재 활성 경고가 없습니다.";
    clearBtn.disabled = true;
    return;
  }

  clearBtn.disabled = false;
  el.className = `active-alert has-alert level-${alert.level}`;
  el.innerHTML = "";

  const info = document.createElement("div");
  info.innerHTML =
    `<div><strong>${LEVEL_LABEL[alert.level] || alert.level}</strong> - ${REASON_LABEL[alert.reason] || alert.reason}</div>` +
    `<div>발생 시각: ${escapeHtml(alert.ts)}</div>` +
    `<div>세션: ${escapeHtml(alert.session_id)} / 대상: ${escapeHtml(alert.track_id || "-")}</div>`;
  el.appendChild(info);

  if (alert.snapshot_path) {
    const img = document.createElement("img");
    img.className = "snapshot";
    img.src = "/api/snapshot?path=" + encodeURIComponent(alert.snapshot_path);
    img.alt = "경고 스냅샷";
    img.onerror = () => {
      img.remove();
      const noSnap = document.createElement("div");
      noSnap.className = "no-snapshot";
      noSnap.textContent = "스냅샷 없음 (파일을 찾을 수 없음)";
      el.appendChild(noSnap);
    };
    el.appendChild(img);
  } else {
    const noSnap = document.createElement("div");
    noSnap.className = "no-snapshot";
    noSnap.textContent = "스냅샷 없음";
    el.appendChild(noSnap);
  }
}

function renderHistory(alerts) {
  const body = document.getElementById("historyBody");
  body.innerHTML = "";
  if (!alerts || alerts.length === 0) {
    body.innerHTML = '<tr><td colspan="5" class="empty">아직 경고 이력이 없습니다.</td></tr>';
    return;
  }
  for (const a of alerts) {
    const tr = document.createElement("tr");

    const tdTime = document.createElement("td");
    tdTime.textContent = a.ts;

    const tdLevel = document.createElement("td");
    const levelBadge = document.createElement("span");
    levelBadge.className = "badge " + a.level;
    levelBadge.textContent = LEVEL_LABEL[a.level] || a.level;
    tdLevel.appendChild(levelBadge);

    const tdReason = document.createElement("td");
    tdReason.textContent = REASON_LABEL[a.reason] || a.reason;

    const tdSession = document.createElement("td");
    tdSession.textContent = `${a.session_id} / ${a.track_id || "-"}`;

    const tdResolved = document.createElement("td");
    const resBadge = document.createElement("span");
    resBadge.className = "badge " + (a.resolved ? "resolved" : "unresolved");
    resBadge.textContent = a.resolved ? "해제됨" : "미해결";
    tdResolved.appendChild(resBadge);

    tr.append(tdTime, tdLevel, tdReason, tdSession, tdResolved);
    body.appendChild(tr);
  }
}

function renderEmergency(active) {
  const banner = document.getElementById("emergencyBanner");
  banner.hidden = !active;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

async function poll() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    const data = await res.json();
    renderMqtt(data.mqtt_connected);
    renderNodes(data.nodes);
    renderVisitor(data.current_visitor);
    renderStatus(data.current_visitor);
    renderActiveAlert(data.active_alert);
    renderHistory(data.recent_alerts);
    renderEmergency(data.emergency_stop);
  } catch (err) {
    renderMqtt(false);
    console.error("상태 조회 실패:", err);
  }
}

document.getElementById("clearAlertBtn").addEventListener("click", async () => {
  const res = await fetch("/api/actions/clear_alert", { method: "POST" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    alert(data.message || "경고 해제에 실패했습니다.");
  }
  poll();
});

document.getElementById("emergencyStopBtn").addEventListener("click", async () => {
  const confirmed = confirm(
    "정말로 긴급 정지를 실행하시겠습니까?\n이 동작은 D 로봇에 EMERGENCY_STOP 명령을 보냅니다."
  );
  if (!confirmed) return;
  await fetch("/api/actions/emergency_stop", { method: "POST" });
  poll();
});

document.getElementById("emergencyResetBtn").addEventListener("click", async () => {
  await fetch("/api/actions/emergency_reset", { method: "POST" });
  poll();
});

poll();
setInterval(poll, POLL_INTERVAL_MS);
