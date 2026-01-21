Local testing

1. Copy `.env.example` to `.env` and fill values (GitHub token, Teams webhook, AWX URL/token if available).

2. Create and activate a Python virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Run the FastAPI app locally:

```powershell
uvicorn app.main:app --reload --port 8000
```

4. Test endpoints:
- Health: `GET http://localhost:8000/health`
- Analyze: `POST http://localhost:8000/analyze_log` with JSON {"source":"awx","log":"..."}

## After server reboot / re-deploy checklist

If the host or server was rebooted, follow these steps to bring the agent back and verify integration end-to-end.

1) Ensure environment variables in `.env` are correct (important values):

- `APP_HOST` — set to the agent host IP (e.g. 192.168.1.200)
- `APP_PORT` — default `8000`
- `AWX_URL` — use the AWX UI/API base (use `http://` if AWX is not serving TLS on that host/port)
- `AWX_TOKEN` — AWX API token
- `AWX_VERIFY` — `false` if AWX uses plain HTTP or an untrusted cert
- `AWX_TIMEOUT` — seconds for AWX API calls (default 10)
- `TEAMS_WEBHOOK_URL` — your Microsoft Teams incoming webhook URL
- `GITHUB_TOKEN` — token with `repo`/`issues` scope if you want server-side issue creation
- Optional: `GITHUB_REPO` and `GITHUB_ORG` if AWX project SCM does not point to GitHub

2) Start the Python venv and dependencies (Windows PowerShell example):

```powershell
cd \path\to\repo
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3) Start the FastAPI app (PowerShell):

```powershell
# prefer running from the activated venv so .env loader picks up the local .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Note: `app.main` now auto-loads `.env` at startup if variables are not already exported.

4) Sanity checks (from any machine that can reach the agent host):

```bash
# Health
curl -v "http://<APP_HOST>:<APP_PORT>/health"

# Fetch AWX job events (replace JOB_ID)
curl -v "http://<APP_HOST>:<APP_PORT>/awx/jobs/14"

# View assembled stdout (plain text)
curl -v "http://<APP_HOST>:<APP_PORT>/awx/jobs/14/stdout"
```

5) Test webhook / E2E flow (simulate AWX webhook):

```bash
curl -i -X POST "http://<APP_HOST>:<APP_PORT>/awx/webhook" -H "Content-Type: application/json" -d '{"id":14,"status":"failed"}'
```

Watch the agent terminal (uvicorn) for logs mentioning:
- `AWXClient.get_job_events:` debug output when contacting AWX
- `AWX job <id> processed.` when background processing runs
- Any `teams.send_awx_notification_card failed:` lines if delivery failed

6) Verify Teams card and actions

- The Adaptive Card will include `View Output` (opens AWX UI if configured, otherwise the agent `/awx/jobs/{id}/stdout`).
- The `Open GH issue` button will call the agent endpoint `/issues/open_from_job?job_id={id}` which creates the issue server-side. Ensure `GITHUB_TOKEN` is valid and the AWX project's SCM URL points to GitHub or set `GITHUB_ORG`/`GITHUB_REPO`.

7) If card shows LLM unavailable message, check `OLLAMA_URL` in `.env` and that the LLM service is running/accessible.

8) If you need to reproduce a failing job, re-run the job in AWX or change `status` in the webhook payload when using the synthetic POST above.

Troubleshooting hints
- If `/awx/jobs/{id}` returns 404: confirm `AWX_URL` is reachable from the agent host and uses the proper scheme (`http` vs `https`).
- If Teams cards do not appear: run `scripts/test_send_teams.py` from the venv to validate webhook delivery.
- If GitHub issue creation fails with 404: ensure `GITHUB_TOKEN` has correct scopes and that `GITHUB_ORG`/`GITHUB_REPO` or AWX project's SCM points to a real GitHub repository.

If you want, I can add a small health-check script that validates AWX, Teams and GitHub connectivity and prints a short report.

5. Docker compose:

```powershell
docker compose up --build
```

The app will be exposed on port 8000 and Postgres on 5432.
