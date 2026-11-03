# Deploying Agent Studio

Agent Studio is designed as a **single-operator** tool: it has no built-in
authentication and its agents **execute code**. This guide deploys it to one
Docker host, behind TLS and a Basic Auth gate, with the per-task sandbox enabled.
Read the [Security model](#security-model) before exposing it to a network.

## What you get

`docker compose up` builds and runs four containers:

| Service | Image | Purpose |
| --- | --- | --- |
| `caddy` | `caddy:2.8` | TLS termination, HTTP Basic Auth, reverse proxy |
| `web`   | built from `web/` | Next.js UI (`:3000`, internal) |
| `api`   | built from `api/` | FastAPI backend (`:8000`, internal) |
| — | `node:22-bookworm` | per-task **sandbox**, launched on demand via the host Docker daemon |

The browser talks only to Caddy; `/api/*` is proxied to the API, everything else to the web app.

## Prerequisites

- A Linux host with **Docker** + the Compose plugin.
- Ports **80/443** open. For automatic HTTPS, a **domain** pointing at the host.
- Outbound network to your model provider (OpenAI/Gemini), the npm registry, and GitHub.

## Steps

```bash
git clone <your-repo-url> && cd Atelier-V2

# 1. Config
cp deploy/.env.example .env
#    Edit .env: set PUBLIC_URL, SITE_ADDRESS, ATELIER_DATA_DIR, DATABASE_URL.

# 2. Basic Auth gate (the only thing keeping the app private)
docker run --rm caddy:2.8 caddy hash-password --plaintext 'your-strong-password'
#    Put the hash in .env as BASIC_AUTH_HASH and set BASIC_AUTH_USER.

# 3. Persistent data dir (must match ATELIER_DATA_DIR in .env)
sudo mkdir -p /srv/atelier && sudo chown "$(id -u)":"$(id -g)" /srv/atelier

# 4. Build and run
docker compose build
docker compose up -d
```

Open `PUBLIC_URL`, sign in with the Basic Auth credentials, then add your model key
at **Settings → Providers**. Create a project from a template and start chatting.

### Local trial without a domain

In `.env` set `SITE_ADDRESS=:80` and `PUBLIC_URL=http://localhost`, then
`docker compose up --build` and open <http://localhost>.

## How data persists

Everything lives under `ATELIER_DATA_DIR` (default `/srv/atelier`), bind-mounted at the
**same path** inside the API container:

- `db/atelier.db` — the SQLite database (schema auto-creates on first run; no migration step).
- `projects/` — one git repo per project, plus `projects/.secrets/` (provider keys & GitHub tokens, `0600`).
- `home/.atelier/` — the sandbox build cache.

Back up `ATELIER_DATA_DIR` to back up the whole deployment. Caddy's certificates persist
in the `caddy_data` volume.

## Security model

**This deployment trusts whoever gets past the Basic Auth gate.** Specifically:

- **No app-level auth / multi-tenancy.** The Basic Auth gate in Caddy is the only
  access control, and every user shares the same projects and keys. Put a real
  identity-aware proxy / SSO in front before more than a trusted operator uses it.
- **Agents execute code.** Each task runs in an isolated `node:22` container on an
  internal Docker network whose only egress is an allow-list proxy (npm, GitHub,
  preview host). This is the safe path and is **on** when `/var/run/docker.sock` is
  mounted (it is, in compose). Mounting the socket gives the API container
  root-equivalent control of the host — acceptable for a dedicated single-tenant VM,
  not for untrusted users.
- **Never run `FORCE_LOCAL=1` in the cloud** — that runs generated code directly in
  the API container instead of the sandbox.
- **Secrets** (provider keys, GitHub tokens) are stored by reference, encrypted/`0600`,
  and never sent to the browser or the model.

## Known limitations / follow-ups

- **Live preview is not exposed.** Preview dev-servers bind to `127.0.0.1` on random
  ports inside the API container, so the in-app preview link isn't reachable from the
  browser yet. Exposing it needs a dynamic reverse-proxy per preview (future work).
- **Single instance.** The API holds a process-wide lock and uses local files, so run
  **one** `api` replica. Scaling out needs Postgres + shared/object storage for
  `projects/` and a rework of the lock and preview model.
- **SQLite by default.** Fine for a single instance; switch `DATABASE_URL` to Postgres
  (see `.env.example`) when you want managed, backed-up storage.

## Updating

```bash
git pull
docker compose build
docker compose up -d
```
