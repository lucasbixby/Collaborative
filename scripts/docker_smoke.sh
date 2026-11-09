#!/usr/bin/env bash
# End-to-end check of the Docker setup (#23): clean build, the web UI (#22), accounts and rooms
# (#16-#18), relay, restart, volume, non-root.
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
USERNAME=smoke
PASSWORD=smoke-password
TOKEN=""
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
[[ "$(curl -fsS -m 2 http://localhost:8000/)" == *'<div id="root">'* ]] || fail "/ doesn't serve the web UI"
pass "/ serves the web UI (#22)"
[[ "$(curl -fsS -m 2 http://localhost:8000/join/anything)" == *'<div id="root">'* ]] || fail "/join/anything doesn't fall back to the app"
pass "a client route (/join/anything) falls back to index.html"
api_404="$(curl -sS -m 2 -o /dev/null -w '%{http_code} %{content_type}' http://localhost:8000/api/nope)"
[[ "$api_404" == "404 application/json" ]] || fail "/api/nope gave $api_404, not a JSON 404"
pass "an unknown /api route is still a JSON 404"
# Not a pipe into grep -q: it quits at the first match, and pipefail then fails on the SIGPIPE.
[[ "$(docker compose logs server)" == *COLLAB_SECRET_KEY* ]] || fail "no secret-key warning in the logs"
pass "the default secret key is warned about"

# The smoke client runs in the container, signed in through COLLAB_TOKEN (empty: signed out).
smoke_client() { docker compose exec -T -e COLLAB_TOKEN="$TOKEN" server python - "$@" < scripts/smoke_client.py; }
as_token() { local saved="$TOKEN"; TOKEN="$1"; shift; smoke_client "$@"; local status=$?; TOKEN="$saved"; return $status; }

# FastAPI's JSON is compact, so the token is the text between "token":" and the next quote.
json_token() { sed -n 's/.*"token":"\([^"]*\)".*/\1/p'; }

api() {  # api METHOD PATH [JSON]: a REST call as $USERNAME, printing the body
  curl -fsS -m 5 -X "$1" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    ${3:+-d "$3"} "http://localhost:8000$2"
}

step "3a. register, sign in and create room $ROOM over REST"
credentials="{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}"
curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d "$credentials" \
  http://localhost:8000/api/auth/register >/dev/null || fail "register failed"
TOKEN="$(curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d "$credentials" \
  http://localhost:8000/api/auth/login | json_token)"
[[ -n "$TOKEN" ]] || fail "login returned no token"
[[ "$(api GET /api/auth/me)" == *"\"username\":\"$USERNAME\""* ]] || fail "/api/auth/me doesn't know the token"
pass "registered $USERNAME and got a token"
[[ "$(api POST /api/rooms "{\"room_id\":\"$ROOM\"}")" == *'"role":"owner"'* ]] || fail "couldn't create room $ROOM"
pass "created room $ROOM, owned by $USERNAME"
as_token "" refused "$ROOM" 4401 || fail "a socket without a token wasn't refused with 4401"
pass "a socket without a token is closed with 4401"
outsider="$(docker compose exec -T -e COLLAB_PASSWORD="$PASSWORD" server sh -c \
  'python scripts/admin.py create-user outsider >/dev/null && python scripts/admin.py token outsider')" \
  || fail "admin.py couldn't make a second user"
as_token "$outsider" refused "$ROOM" 4403 || fail "a non-member wasn't refused with 4403"
pass "a signed-in non-member is closed with 4403 (user made with admin.py)"

step "3b. relay between two clients in room $ROOM"
smoke_client relay "$ROOM" || fail "relay check failed"
pass "second client received the operations"
expect_log_count 3

step "4a. stop with a client connected exits cleanly and quickly"
smoke_client hold "$ROOM" &
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
