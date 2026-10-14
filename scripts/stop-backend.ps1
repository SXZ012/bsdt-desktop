$taskRoot=Split-Path $PSScriptRoot -Parent
$taskPidFile=Join-Path $taskRoot 'runtime\backend.pid'
if (Test-Path -LiteralPath $taskPidFile) {
    $taskBackendPid=[int](Get-Content -LiteralPath $taskPidFile)
    $taskProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$taskBackendPid"
    if ($taskProcess -and $taskProcess.CommandLine -like '*uvicorn backend.app:app*' -and $taskProcess.ExecutablePath -eq (Join-Path $taskRoot '.venv\Scripts\python.exe')) {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$taskBackendPid" | Where-Object { $_.CommandLine -like '*uvicorn backend.app:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $taskBackendPid -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $taskPidFile
}
