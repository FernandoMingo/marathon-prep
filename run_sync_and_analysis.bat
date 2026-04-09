@echo off
setlocal

cd /d "%~dp0"

set "SYNC_LOG=%TEMP%\strava_sync_%RANDOM%_%RANDOM%.log"
set "NEW_ACTIVITIES=0"

echo [1/3] Sincronizando actividades desde Strava API...
py "sync_strava.py" > "%SYNC_LOG%" 2>&1
type "%SYNC_LOG%"
if errorlevel 1 (
  echo Error en sync_strava.py
  del "%SYNC_LOG%" >nul 2>&1
  exit /b 1
)

for /f "tokens=3 delims=: " %%A in ('findstr /c:"Actividades nuevas:" "%SYNC_LOG%"') do (
  set "NEW_ACTIVITIES=%%A"
)
del "%SYNC_LOG%" >nul 2>&1

echo [2/3] Ejecutando analisis...
py "analisis.py" --strava "strava_sync/activities.csv"
if errorlevel 1 (
  echo Error en analisis.py
  exit /b 1
)

if "%NEW_ACTIVITIES%"=="0" (
  echo [3/3] Sin actividades nuevas de Strava. Se omite auto-publicado.
) else (
  echo [3/3] Actividades nuevas detectadas ^(%NEW_ACTIVITIES%^). Publicando cambios...
  py "auto_publish_docs.py"
  if errorlevel 1 (
    echo Error en auto_publish_docs.py
    exit /b 1
  )
)

echo Proceso completado.
exit /b 0
