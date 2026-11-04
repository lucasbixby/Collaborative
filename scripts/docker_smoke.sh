#!/usr/bin/env bash
# End-to-end check of the Docker setup (#23): clean build, relay, restart, volume, non-root.
#
#   scripts/docker_smoke.sh
#
# Runs as its own Compose project with its own volume, so it never touches the data of your usual
# `docker compose up`. It does need port 8000, so stop that server first. Takes about a minute.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export COMPOSE_PROJECT_NAME=collaborative-smoke
export COLLAB_SECRET_KEY=dev-only-change-me  # the default, whatever a local .env says
VOLUME="${COMPOSE_PROJECT_NAME}_server-data"
ROOM=demo
STOP_LIMIT=5  # seconds; Docker's kill comes at 10

step() { printf '\n== %s\n' "$*"; }
pass() { printf '   ok: %s\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*" >&2; docker compose logs --tail 30 server >&2 || true; exit 1; }

cleanup() {
  printf '\n== cleaning up\n'
  docker compose down -v --rmi local --remove-orphans >/dev/null 2>&1 || true
}

wait_healthy() {
  local status="" _
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -aq server)" 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then pass "container is healthy"; return; fi
    sleep 1
  done
  fail "container not healthy after 60 s (last status: ${status:-none})"
}

expect_log_count() {
  local output
  output="$(docker compose exec -T server python scripts/show_log.py "$ROOM")" || fail "show_log.py failed: $output"
  [[ "$output" == *"$1 operation(s) in room '$ROOM'"* ]] || fail "expected $1 operation(s), got: $output"
  pass "show_log.py lists $1 operation(s) in room $ROOM"
}

if curl -fsS -m 2 http://localhost:8000/health >/dev/null 2>&1; then
  printf 'Something is already serving on port 8000. Stop it first (docker compose down keeps its data).\n' >&2
  exit 1
fi

trap cleanup EXIT

step "1. clean build, no cache, fresh volume"
docker compose down -v --remove-orphans >/dev/null 2>&1
docker compose build --no-cache --pull server

step "2. start and wait for healthy"
docker compose up -d
wait_healthy
curl -fsS -m 2 http://localhost:8000/health >/dev/null || fail "/health isn't reachable from the host on port 8000"
pass "/health answers on the published port"
# Not a pipe into grep -q: it quits at the first match, and pipefail then fails on the SIGPIPE.
[[ "$(docker compose logs server)" == *COLLAB_SECRET_KEY* ]] || fail "no secret-key warning in the logs"
pass "the default secret key is warned about"

step "3. relay between two clients in room $ROOM"
docker compose exec -T server python - relay "$ROOM" < scripts/smoke_client.py || fail "relay check failed"
pass "second client received the operations"
expect_log_count 3

step "4a. stop with a client connected exits cleanly and quickly"
docker compose exec -T server python - hold "$ROOM" < scripts/smoke_client.py &
holder=$!
sleep 2
kill -0 "$holder" 2>/dev/null || fail "the connected client exited early"
started=$SECONDS
docker compose stop server
elapsed=$((SECONDS - started))
exit_code="$(docker inspect -f '{{.State.ExitCode}}' "$(docker compose ps -aq server)")"
wait "$holder" || true
[[ "$exit_code" == "0" ]] || fail "exit code $exit_code (137 means Docker had to kill it)"
((elapsed <= STOP_LIMIT)) || fail "stop took ${elapsed}s, limit ${STOP_LIMIT}s"
pass "stopped in ${elapsed}s, exit code 0"
docker compose start server
wait_healthy

step "4b. history survives docker compose restart"
docker compose restart server
wait_healthy
expect_log_count 3

step "5a. history survives down and up (volume kept)"
docker compose down
docker compose up -d
wait_healthy
expect_log_count 3

step "6. runs as non-root, and owns its data"
user="$(docker compose exec -T server id -u)"
[[ "$user" != "0" ]] || fail "the server is running as root"
pass "uid $user: $(docker compose exec -T server id -un)"
owner="$(docker compose exec -T server stat -c %u /srv/data/assets)"
[[ "$owner" == "$user" ]] || fail "/srv/data/assets is owned by uid $owner, not $user"
pass "/srv/data/assets on the volume belongs to uid $user"

step "5b. down -v removes the history"
docker compose down -v
if docker volume inspect "$VOLUME" >/dev/null 2>&1; then fail "volume $VOLUME still exists"; fi
pass "volume $VOLUME is gone"
docker compose up -d
wait_healthy
expect_log_count 0

printf '\nAll checks passed.\n'
