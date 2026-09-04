#!/usr/bin/env bash
# API entrypoint: wait for Postgres, run migrations, then exec the given command.
set -euo pipefail

echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432} ..."
python - <<'PY'
import os, socket, time
host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("[entrypoint] postgres is up")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("[entrypoint] postgres never became reachable")
PY

echo "[entrypoint] running database migrations ..."
alembic upgrade head

exec "$@"
