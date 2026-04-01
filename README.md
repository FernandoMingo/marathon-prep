# Analisis Futbol + Maraton (VIBE CODED AS HELL)

Proyecto para unificar:
- sesiones de futbol (GPS/carga),
- actividades de Strava (desde Garmin via sync),
- plan de maraton,
- y publicar un dashboard en GitHub Pages.

## Estructura

- `analisis.py`: pipeline principal de analitica y predicciones.
- `sync_strava.py`: sync incremental por API de Strava (OAuth + refresh token).
- `run_sync_and_analysis.bat`: sync + analisis en un solo comando.
- `setup_strava_task.ps1`: crea tarea de Windows cada 2 dias.
- `docs/`: sitio estatico para GitHub Pages.
  - `index.html`, `styles.css`, `app.js`
  - `assets/` (graficos + plan PDF)
  - `data/` (csv y metadatos)
- `analysis_output/`: salida tecnica completa del pipeline.
- `logs/`: logs de ejecucion.

## Configuracion

1. Crear `.env` en raiz:

```env
STRAVA_CLIENT_ID=tu_client_id
STRAVA_CLIENT_SECRET=tu_client_secret
```

2. Primera autorizacion OAuth:

```powershell
py sync_strava.py
```

3. Ejecutar analisis + publicacion:

```powershell
py analisis.py --strava "strava_sync/activities.csv" --site-dir "docs" --plan-pdf "plan_maraton_hibrido_visual.pdf"
```

4. (Opcional) Automatizar cada 2 dias:

```powershell
powershell -ExecutionPolicy Bypass -File setup_strava_task.ps1
```

5. Auto-publicacion en GitHub (si hay cambios en `docs/`):

- El runner `run_sync_and_analysis.bat` ejecuta `auto_publish_docs.py`.
- Requisitos:
  - Tener remoto `origin` configurado.
  - Tener autenticacion git operativa en tu maquina (GitHub Desktop / PAT / SSH).
- Configurable en `.env`:
  - `GITHUB_AUTO_PUBLISH=1` (o `0` para desactivar).

## Publicar en GitHub Pages

En GitHub:
1. `Settings` -> `Pages`
2. Source: `Deploy from a branch`
3. Branch: `main` y carpeta `/docs`

El dashboard quedara en la URL de Pages del repo.
