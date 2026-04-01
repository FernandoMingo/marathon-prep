import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "publish.log"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        ["git", *args],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
    return cp


def main() -> None:
    setup_logging()
    load_dotenv(ENV_PATH)
    enabled = os.getenv("GITHUB_AUTO_PUBLISH", "1").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        logging.info("Auto publish disabled by GITHUB_AUTO_PUBLISH.")
        return

    run_git(["rev-parse", "--is-inside-work-tree"])
    remote = run_git(["remote", "get-url", "origin"], check=False)
    if remote.returncode != 0 or not remote.stdout.strip():
        raise RuntimeError("No git remote 'origin' configured. Add remote before auto-publish.")

    branch = run_git(["branch", "--show-current"]).stdout.strip() or "master"

    # Publish only the website output for GitHub Pages.
    run_git(["add", "docs"])
    staged_diff = run_git(["diff", "--cached", "--name-only"]).stdout.strip()
    if not staged_diff:
        logging.info("No changes in docs/. Nothing to publish.")
        print("No updates to publish.")
        return

    msg = f"chore: update dashboard site ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    run_git(["commit", "-m", msg])
    push_try = run_git(["push", "origin", branch], check=False)
    if push_try.returncode != 0:
        # first publish on a new local branch might require -u
        push_try = run_git(["push", "-u", "origin", branch], check=False)
        if push_try.returncode != 0:
            raise RuntimeError(push_try.stderr.strip() or "git push failed")

    logging.info("Published docs changes to origin/%s", branch)
    print(f"Published updates to origin/{branch}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Auto publish failed: %s", exc)
        raise
