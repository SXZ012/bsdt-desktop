param([string]$Inbox='', [int]$Port=8765)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$taskPython=Join-Path $taskRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) { throw '缺少后台环境，请先按 README 安装 Python 依赖。' }
$taskRuntime=Join-Path $taskRoot 'runtime'
New-Item -ItemType Directory -Force -Path $taskRuntime | Out-Null
$taskConfigPath=Join-Path $taskRuntime 'server-config.json'
if ($Inbox) {
    @{inbox=$Inbox} | ConvertTo-Json | Set-Content -LiteralPath $taskConfigPath -Encoding UTF8
    $env:BSDT_INBOX=$Inbox
} elseif (Test-Path -LiteralPath $taskConfigPath) {
    $taskConfig=Get-Content -Raw -LiteralPath $taskConfigPath | ConvertFrom-Json
    if ($taskConfig.inbox) { $env:BSDT_INBOX=$taskConfig.inbox }
}
$env:BSDT_DATA_DIR=$taskRuntime
$env:PYTHONIOENCODING='utf-8'
try { $taskHealth=Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2; if ($taskHealth.scan_interval_seconds) { Write-Host "后台已运行：http://127.0.0.1:$Port"; exit 0 } } catch {}
$taskProcess=Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','backend.app:app','--host','0.0.0.0','--port',"$Port") -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntime 'backend.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'backend.stderr.log') -PassThru
$taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskRuntime 'backend.pid')
for ($taskAttempt=0;$taskAttempt -lt 20;$taskAttempt++) { Start-Sleep -Milliseconds 500; if ($taskProcess.HasExited) { throw '后台启动失败，请查看 runtime/backend.stderr.log' }; try { Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1 | Out-Null; Write-Host "后台已启动：http://127.0.0.1:$Port，局域网客户端请填写此电脑的 IPv4 地址。"; exit 0 } catch {} }
throw '后台未在预期时间内响应，请查看日志。'
