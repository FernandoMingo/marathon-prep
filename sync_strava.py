import csv
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SYNC_DIR = BASE_DIR / "strava_sync"
ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "strava_sync.log"
TOKEN_PATH = SYNC_DIR / "strava_tokens.json"
STATE_PATH = SYNC_DIR / "sync_state.json"
OUT_CSV = SYNC_DIR / "activities.csv"
REDIRECT_URI = "http://localhost:8765/callback"
AUTH_SCOPE = "read,activity:read_all"


CSV_COLUMNS = [
    "Activity ID",
    "Activity Date",
    "Activity Name",
    "Activity Type",
    "Distance",
    "Distance.1",
    "Moving Time",
    "Average Heart Rate",
    "Relative Effort",
    "Max Heart Rate",
    "Elapsed Time",
    "Average Speed",
    "Max Speed",
    "Elevation Gain",
    "Start Time",
]


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def now_epoch() -> int:
    return int(time.time())


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def http_json(url: str, method: str = "GET", data: dict | None = None, headers: dict | None = None) -> dict:
    payload = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if data is not None:
        payload = urllib.parse.urlencode(data).encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(url=url, method=method, data=payload, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def read_config() -> tuple[str, str]:
    load_dotenv(ENV_PATH)
    client_id = str(os.getenv("STRAVA_CLIENT_ID", "")).strip()
    client_secret = str(os.getenv("STRAVA_CLIENT_SECRET", "")).strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Faltan credenciales de Strava.\n"
            f"Define STRAVA_CLIENT_ID y STRAVA_CLIENT_SECRET en {ENV_PATH}.\n"
            "Ejemplo:\n"
            "STRAVA_CLIENT_ID=12345\n"
            "STRAVA_CLIENT_SECRET=tu_secret"
        )
    return client_id, client_secret


class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None
    done_event = threading.Event()

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        query = urllib.parse.parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        if code:
            OAuthHandler.auth_code = code
            OAuthHandler.done_event.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Autorizacion completada.</h2><p>Ya puedes cerrar esta ventana.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


def get_authorization_code(client_id: str) -> str:
    OAuthHandler.auth_code = None
    OAuthHandler.done_event.clear()
    server = HTTPServer(("localhost", 8765), OAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": AUTH_SCOPE,
    }
    auth_url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode(params)
    print("Abriendo navegador para autorizar Strava...")
    logging.info("Abriendo navegador para OAuth de Strava")
    webbrowser.open(auth_url)

    ok = OAuthHandler.done_event.wait(timeout=180)
    server.shutdown()
    server.server_close()
    if not ok or not OAuthHandler.auth_code:
        raise RuntimeError("No se recibió el code OAuth en 180 segundos.")
    return OAuthHandler.auth_code


def exchange_code_for_token(client_id: str, client_secret: str, code: str) -> dict:
    return http_json(
        "https://www.strava.com/oauth/token",
        method="POST",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
    )


def refresh_token(client_id: str, client_secret: str, refresh: str) -> dict:
    return http_json(
        "https://www.strava.com/oauth/token",
        method="POST",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        },
    )


def ensure_access_token() -> str:
    client_id, client_secret = read_config()
    token = load_json(TOKEN_PATH)

    if not token.get("access_token"):
        code = get_authorization_code(client_id)
        token = exchange_code_for_token(client_id, client_secret, code)
        save_json(TOKEN_PATH, token)
        return token["access_token"]

    expires_at = int(token.get("expires_at", 0))
    if expires_at < now_epoch() + 120:
        token = refresh_token(client_id, client_secret, token["refresh_token"])
        save_json(TOKEN_PATH, token)
    return token["access_token"]


def parse_date_to_epoch(s: str) -> int | None:
    if not s:
        return None
    dt = None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    return int(dt.timestamp())


def fetch_activities(access_token: str, after_epoch: int | None) -> list[dict]:
    activities = []
    page = 1
    while True:
        params = {"per_page": 200, "page": page}
        if after_epoch:
            params["after"] = after_epoch
        url = "https://www.strava.com/api/v3/athlete/activities?" + urllib.parse.urlencode(params)
        batch = http_json(url, headers={"Authorization": f"Bearer {access_token}"})
        if not isinstance(batch, list) or len(batch) == 0:
            break
        activities.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    return activities


def strava_to_row(a: dict) -> dict:
    dist_m = float(a.get("distance", 0.0) or 0.0)
    dist_km = dist_m / 1000.0
    dt = a.get("start_date_local") or a.get("start_date") or ""
    date_text = ""
    if dt:
        try:
            date_text = datetime.fromisoformat(dt.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            date_text = dt

    return {
        "Activity ID": str(a.get("id", "")),
        "Activity Date": date_text,
        "Activity Name": str(a.get("name", "")),
        "Activity Type": str(a.get("type", "")),
        "Distance": f"{dist_km:.5f}",
        "Distance.1": f"{dist_m:.1f}",
        "Moving Time": str(int(a.get("moving_time", 0) or 0)),
        "Average Heart Rate": str(a.get("average_heartrate", "") or ""),
        "Relative Effort": str(a.get("suffer_score", "") or ""),
        "Max Heart Rate": str(a.get("max_heartrate", "") or ""),
        "Elapsed Time": str(int(a.get("elapsed_time", 0) or 0)),
        "Average Speed": str(a.get("average_speed", "") or ""),
        "Max Speed": str(a.get("max_speed", "") or ""),
        "Elevation Gain": str(a.get("total_elevation_gain", "") or ""),
        "Start Time": dt,
    }


def read_existing_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aid = str(row.get("Activity ID", "")).strip()
            if aid:
                out[aid] = row
    return out


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: r.get("Activity Date", ""))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows_sorted)


def main() -> None:
    setup_logging()
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_PATH)
    after_epoch = state.get("last_sync_epoch")
    logging.info("Inicio sync Strava. out_csv=%s", OUT_CSV)

    if not after_epoch and OUT_CSV.exists():
        existing = read_existing_rows(OUT_CSV)
        epochs = []
        for row in existing.values():
            epoch = parse_date_to_epoch(str(row.get("Start Time", "")))
            if epoch:
                epochs.append(epoch)
        if epochs:
            after_epoch = max(epochs) - 86400

    logging.info("Sync incremental after_epoch=%s", after_epoch)
    token = ensure_access_token()
    new_activities = fetch_activities(token, after_epoch)
    logging.info("Actividades descargadas: %d", len(new_activities))

    existing_map = read_existing_rows(OUT_CSV)
    for act in new_activities:
        row = strava_to_row(act)
        aid = row["Activity ID"]
        if aid:
            existing_map[aid] = row

    all_rows = list(existing_map.values())
    write_rows(OUT_CSV, all_rows)

    state["last_sync_epoch"] = now_epoch()
    state["last_total_rows"] = len(all_rows)
    save_json(STATE_PATH, state)

    logging.info("Sync completado. total_guardadas=%d", len(all_rows))
    print(f"Sync completado. Actividades nuevas: {len(new_activities)}")
    print(f"Total guardadas en {OUT_CSV}: {len(all_rows)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Error en sync_strava.py: %s", exc)
        raise
