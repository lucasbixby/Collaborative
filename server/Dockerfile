FROM python:3.12-slim

WORKDIR /srv

# Dependencies get their own layer, built from pyproject.toml alone, so editing code doesn't
# reinstall them. `app` isn't installed as a package: it runs from /srv, like in local dev.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY app ./app
COPY scripts ./scripts

# A fresh named volume copies the ownership of the folder it's mounted on, so this has to happen
# before VOLUME. A volume first created by an older, root-run image stays root-owned: `down -v`.
RUN useradd --system --no-create-home --uid 10001 collab \
    && mkdir -p /srv/data/assets \
    && chown -R collab:collab /srv/data
USER collab
VOLUME ["/srv/data"]

EXPOSE 8000

# The slim image has no curl. urlopen raises on a connection failure or an error status.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 --start-period=30s --start-interval=1s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# One worker on purpose: rooms (ConnectionManager) and origin pins (OriginRegistry) live in this
# process's memory, so a second worker would split a room in two, with clients on different
# workers never seeing each other's edits. SQLite also has only one writer at a time.
# Exec form, so uvicorn is PID 1 and receives SIGTERM from `docker compose stop`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
