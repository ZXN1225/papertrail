# Single-server deployment

This runbook deploys the existing Docker Compose application on one Linux VPS. It keeps the API private to the Compose network, stores SQLite and uploaded PDFs in the existing persistent data volume, and uses Caddy for HTTPS. It is a small production setup, not a high-availability or multi-host design.

## Before deployment

- Create a Linux VPS with Docker Engine and the Docker Compose plugin. Keep one backend process; SQLite and the in-process PDF worker are not configured for horizontal scaling.
- Point a DNS A/AAAA record for the chosen hostname to the VPS. Allow inbound TCP 80/443 and UDP 443 in the firewall.
- Allocate enough persistent disk for `/data` (SQLite plus private PDFs) and `/models` (MinerU models). Standard MinerU needs several GB for its local models; advanced chart analysis needs additional model storage and more CPU/GPU resources.
- Keep the deployment private until the smoke checks and backup/restore drill below pass.

## Configure secrets and models

Create the root `.env` from `.env.example` on the server without overwriting an existing file. Restrict it to the deployment account (`chmod 600 .env`). Set `PAPERTRAIL_DOMAIN`, `LLM_API_KEY`, and `LLM_MODEL`. The production Compose overlay requires these values and sets `APP_ENV=production`, secure session cookies, bounded LLM timeouts, and a default per-user daily token budget of 24,000 tokens. The budget is a token limit, not a hard dollar cap. Adjust `AGENT_DAILY_USER_TOKEN_BUDGET` to be at least `AGENT_MAX_TOTAL_TOKENS`.

The embedding provider stays disabled unless explicitly configured. BM25 remains available without an embedding key; indexed private papers can use semantic RRF when the embedding provider and vectors are configured.

Build the backend image, then download and verify MinerU models into the persistent `papertrail-models` volume before accepting PDF uploads:

```sh
docker compose build backend web
docker compose run --rm --no-deps backend mineru-kit models download \
  --tier standard --small-backend onnx --vlm-engine llama-cpp --source huggingface
docker compose run --rm --no-deps backend mineru-kit models verify \
  --tier standard --small-backend onnx --vlm-engine llama-cpp
```

The model download command uses the same `/models` volume as the service. The app does not download models while serving a request. Set `PAPERTRAIL_MINERU_TIER=advanced` only after the advanced model set has also been downloaded and verified; otherwise chart/image analysis will not be available. Parser-generated table and visual descriptions remain explicitly unverified evidence.

## Start and verify

```sh
docker compose -f compose.yaml -f compose.production.yaml config --quiet
docker compose -f compose.yaml -f compose.production.yaml up --build -d
docker compose -f compose.yaml -f compose.production.yaml ps
curl --fail --silent --show-error "https://${PAPERTRAIL_DOMAIN}/api/status"
```

Confirm the response reports `ready`, then register a test account and verify login, logout, a metadata search, one licensed PDF upload/parse/retrieval, and an Agent answer with citations. Use synthetic or explicitly authorized test documents. Confirm that session cookies are `Secure`, `HttpOnly`, and `SameSite=Lax` in the browser. Do not test by uploading unlicensed papers.

Caddy obtains and renews certificates for `PAPERTRAIL_DOMAIN`; its official image is pinned to `caddy:2.11.9-alpine`. Keep the Caddy data volume so certificate state survives container recreation. The Web container remains reachable on host loopback at port 3000 for local diagnostics; public traffic should use the Caddy HTTPS endpoint.

## Backups and recovery

Back up the complete `papertrail-data` volume because it contains both `papertrail.sqlite3` and `private-papers/`. Back up the Caddy data/config volumes or be prepared to re-issue certificates. The MinerU model volume is reproducible from the pinned parser/model instructions, but retaining it avoids a multi-GB re-download.

Take a consistent backup while the backend is stopped, encrypt backups at rest, restrict access, and test a restore into a separate volume before treating deployment as production-ready. A snapshot of only the SQLite file is incomplete because it omits uploaded PDFs. Never remove `papertrail-data` during routine upgrades; `docker compose down --volumes` deletes the application data.

## Operational limits

- Run a single backend replica. The current deployment uses SQLite, local file storage, and a single in-process PDF worker; horizontal scaling requires a shared database/object store and distributed worker/limiter design.
- Configure provider secrets only on the server. The default daily token budget reduces per-account usage but does not enforce a dollar hard cap.
- Monitor disk usage, container health, provider errors, and failed PDF jobs. Back up before schema upgrades and keep the prior image available for rollback.
- This repository currently has no configured VPS credentials, DNS name, automated backup destination, or public deployment. Completing this runbook does not itself publish the service.
