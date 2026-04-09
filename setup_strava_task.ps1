$ErrorActionPreference = "Stop"

$taskName = "AnalisisFutbol_StravaSync_2Dias"
$repoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $repoPath "run_sync_and_analysis.bat"
$schtasks = Join-Path $env:WINDIR "System32\schtasks.exe"

if (-not (Test-Path $batPath)) {
    throw "No existe run_sync_and_analysis.bat en $repoPath"
}
if (-not (Test-Path $schtasks)) {
    throw "No se encontro schtasks.exe en $schtasks"
}

$startTime = (Get-Date).AddMinutes(5).ToString("HH:mm")

& $schtasks /Create `
    /TN $taskName `
    /TR "`"$batPath`"" `
    /SC DAILY `
    /MO 1 `
    /ST $startTime `
    /F | Out-Null

Write-Host "Tarea creada: $taskName"
Write-Host "Frecuencia: cada 1 dia(s)"
Write-Host "Inicio: $startTime"
Write-Host "Comando: $batPath"
