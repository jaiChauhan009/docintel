#!/usr/bin/env bash
# Worker entrypoint: wait for postgres + kafka, then start the consumer.
# Migrations are owned by the API container; the worker only waits for them.
set -euo pipefail

python - <<'PY'
import os, socket, time

def wait(host, port, name):
    for _ in range(90):
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                print(f"[worker] {name} is up")
                return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"[worker] {name} never became reachable")

wait(os.getenv("POSTGRES_HOST", "postgres"), os.getenv("POSTGRES_PORT", "5432"), "postgres")
kafka = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(",")[0]
host, _, port = kafka.partition(":")
wait(host, port or "9092", "kafka")
PY

exec "$@"
