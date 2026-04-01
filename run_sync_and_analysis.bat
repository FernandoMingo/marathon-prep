@echo off
setlocal

cd /d "%~dp0"

echo [1/2] Sincronizando actividades desde Strava API...
py "sync_strava.py"
if errorlevel 1 (
  echo Error en sync_strava.py
  exit /b 1
)

echo [2/2] Ejecutando analisis...
py "analisis.py" --strava "strava_sync/activities.csv"
if errorlevel 1 (
  echo Error en analisis.py
  exit /b 1
)

echo [3/3] Publicando cambios en GitHub si hay updates...
py "auto_publish_docs.py"
if errorlevel 1 (
  echo Error en auto_publish_docs.py
  exit /b 1
)

echo Proceso completado.
exit /b 0
