# B 시연 실행기 — 창 하나에 3칸: 파이(B 대화) · 브로커 메시지 · API 서버
#   더블클릭: tools\B_시연_실행.bat   (또는 바탕화면 바로가기)
# 지난번 입력값은 %LOCALAPPDATA%\mechdog_b_demo.json 에 기억한다 (저장소 밖).
# 이 창을 열어 두는 동안 노트북이 잠들지 않는다 — 잠들면 SSH 가 끊겨 B 가 같이 꺼진다.
param([string]$Broker, [string]$Pi, [ValidateSet('', 'gate', 'demo')][string]$Mode = '',
      [switch]$DryRun)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root 'worktrees\api-server\api-server'
$CfgPath = Join-Path $env:LOCALAPPDATA 'mechdog_b_demo.json'
$Tmp = Join-Path $env:TEMP 'mechdog_b_demo'
New-Item -ItemType Directory -Force $Tmp | Out-Null

# --- 입력 (지난번 값이 기본) ---------------------------------------------------
$cfg = [ordered]@{ broker = ''; pi = '192.168.45.236'; mode = 'gate' }
if (Test-Path $CfgPath) {
    try { (Get-Content $CfgPath -Raw | ConvertFrom-Json).psobject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } } catch {}
}
function Ask($label, $def) {
    $v = Read-Host "$label [$def]"
    if ([string]::IsNullOrWhiteSpace($v)) { return $def } else { return $v.Trim() }
}
Write-Host ''
Write-Host '=== B 시연 실행기 ===' -ForegroundColor Cyan
if (-not $Broker) { $Broker = Ask '브로커 IP (A 노트북)' $cfg.broker }
if (-not $Pi) { $Pi = Ask '파이 IP' $cfg.pi }
if (-not $Mode) {
    $d = if ($cfg.mode -eq 'demo') { '2' } else { '1' }
    $m = Ask '모드  1 = 게이트(A 인계를 기다림)  2 = 시연(--demo, 터치로 혼자 시작)' $d
    $Mode = if ($m -eq '2') { 'demo' } else { 'gate' }
}
$User = ''; $Pass = ''
if (-not $DryRun) {
    $User = Read-Host '브로커 계정 (없으면 Enter)'
    if ($User) { $Pass = Read-Host '브로커 비밀번호' }
}
if (-not $Broker) { Write-Host '브로커 IP 가 없습니다.' -ForegroundColor Red; Read-Host 'Enter 로 종료'; exit 1 }
$cfg.broker = $Broker; $cfg.pi = $Pi; $cfg.mode = $Mode
$cfg | ConvertTo-Json | Set-Content $CfgPath -Encoding UTF8

# --- 사전 점검 -------------------------------------------------------------------
function Port($h, $p) {
    try { $c = New-Object Net.Sockets.TcpClient; $ok = $c.ConnectAsync($h, $p).Wait(2000); $c.Close(); return $ok } catch { return $false }
}
Write-Host ''
if (-not (Port $Pi 22)) {
    Write-Host "파이($Pi) 에 SSH 가 안 됩니다 — mechdog-b.local 로 시도" -ForegroundColor Yellow
    $Pi = 'mechdog-b.local'
}
$brokerOk = Port $Broker 1883
Write-Host ("브로커 {0}:1883  {1}" -f $Broker, $(if ($brokerOk) { '열림' } else { '응답 없음 — A 브로커가 떠 있는지 확인' })) -ForegroundColor $(if ($brokerOk) { 'Green' } else { 'Yellow' })
$apiRunning = Port '127.0.0.1' 8080
Write-Host ("API 서버  {0}" -f $(if ($apiRunning) { '이미 실행 중 → 요청 기록만 보여 줌' } else { '새로 띄움' }))

# --- 칸마다 실행할 스크립트 ----------------------------------------------------------
function Q($s) { "'" + ($s -replace "'", "'\''") + "'" }      # bash 작은따옴표
$envs = "MQTT_HOST=$Broker"
if ($User) { $envs = "MQTT_USER=$(Q $User) MQTT_PASS=$(Q $Pass) $envs" }
$runner = if ($Mode -eq 'demo') { '~/run_demo.sh' } else { '~/run_gate.sh' }
$head = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; chcp 65001 > `$null`n"

$pane1 = $head + @"
`$host.UI.RawUI.WindowTitle = 'B 파이'
Write-Host '파이 $Pi · $Mode 모드 · 브로커 $Broker — Ctrl+C 로 종료' -ForegroundColor Cyan
ssh -t -o ServerAliveInterval=15 mechdog@$Pi "$envs $runner"
Write-Host 'B 가 종료됐습니다. 다시 띄우려면 실행기를 다시 여세요.' -ForegroundColor Yellow
"@
$auth = if ($User) { "-u $User -P '$($Pass -replace "'", "''")'" } else { '' }
$pane2 = $head + @"
`$host.UI.RawUI.WindowTitle = '브로커 메시지'
Write-Host '브로커 $Broker 의 mechdog/# 메시지 (B 본체 초음파는 너무 잦아 뺌)' -ForegroundColor Cyan
docker run --rm -i eclipse-mosquitto:2 mosquitto_sub -h $Broker $auth -t 'mechdog/#' -T 'mechdog/internal/b/ultrasonic' -v
"@
if ($apiRunning) {
    $pane3 = $head + @"
`$host.UI.RawUI.WindowTitle = 'API 요청 기록'
Write-Host 'API 감사 로그 (client · path · status)' -ForegroundColor Cyan
`$log = Get-ChildItem '$ApiDir\logs\audit_*.jsonl' | Sort-Object LastWriteTime | Select-Object -Last 1
if (`$log) { Get-Content `$log.FullName -Wait -Tail 20 -Encoding UTF8 } else { Write-Host '아직 요청 없음' }
"@
} else {
    $pane3 = $head + @"
`$host.UI.RawUI.WindowTitle = 'API 서버'
Set-Location '$ApiDir'
Write-Host 'API 서버 http://0.0.0.0:8080 — 확인: http://localhost:8080/healthz' -ForegroundColor Cyan
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8080 --env-file .env
"@
}
$utf8bom = New-Object Text.UTF8Encoding $true
$files = @{}
foreach ($k in 'pane1', 'pane2', 'pane3') {
    $f = Join-Path $Tmp "$k.ps1"; [IO.File]::WriteAllText($f, (Get-Variable $k -ValueOnly), $utf8bom); $files[$k] = $f
}
$ps = 'powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File'
$wtArgs = "-w new new-tab --title B파이 $ps `"$($files.pane1)`" ; split-pane -V --title 브로커 $ps `"$($files.pane2)`" ; split-pane -H --title API $ps `"$($files.pane3)`""

if ($DryRun) {
    Write-Host "`n[DryRun] wt.exe $wtArgs"; foreach ($k in 'pane1', 'pane2', 'pane3') { Write-Host "--- $k"; Get-Content $files[$k] }
    exit 0
}
Start-Process wt.exe -ArgumentList $wtArgs

# --- 잠들지 않게 ---------------------------------------------------------------------
Add-Type -Namespace W -Name P -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[void][W.P]::SetThreadExecutionState([uint32]'0x80000003')     # CONTINUOUS | SYSTEM | DISPLAY
Write-Host ''
Write-Host '실행했습니다. 이 창을 열어 두는 동안 노트북이 잠들지 않습니다.' -ForegroundColor Green
Read-Host '시연이 끝나면 Enter (잠금 방지 해제)'
[void][W.P]::SetThreadExecutionState([uint32]'0x80000000')
