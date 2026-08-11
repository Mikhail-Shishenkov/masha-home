[CmdletBinding()]
param(
    [ValidateSet("chat", "status", "run", "receipts", "background", "stop", "skills", "agent", "observe", "permissions")]
    [string]$Mode = "chat",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Error "Не найдено локальное Python-окружение: $Python"
    exit 1
}

$env:PYTHONUTF8 = "1"

switch ($Mode) {
    "chat" { & $Python -m backend.conversation.cli }
    "status" { & $Python -m backend.runtime.cli status }
    "run" { & $Python -m backend.runtime.cli run }
    "receipts" { & $Python -m backend.runtime.cli receipts }
    "skills" { & $Python -m backend.skills.cli @RemainingArgs }
    "agent" { & $Python -m backend.skills.agent_cli @RemainingArgs }
    "observe" { & $Python -m backend.skills.observe_cli @RemainingArgs }
    "permissions" { & $Python -m backend.skills.permissions_cli @RemainingArgs }
    "background" {
        Start-Process -FilePath $Python -ArgumentList @("-m", "backend.temporal.proactive_daemon", "--project-root", $ProjectRoot) -WorkingDirectory $ProjectRoot -WindowStyle Hidden
        Write-Output "Фоновый Daily Runtime Маши запускается."
    }
    "stop" {
        $StopFile = Join-Path $ProjectRoot "local-data\runtime\proactive-daemon.stop"
        New-Item -ItemType Directory -Force -Path (Split-Path $StopFile) | Out-Null
        Set-Content -LiteralPath $StopFile -Value "stop" -Encoding utf8
        Write-Output "Остановка Daily Runtime запрошена."
    }
}
