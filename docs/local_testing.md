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

5. Docker compose:

```powershell
docker compose up --build
```

The app will be exposed on port 8000 and Postgres on 5432.
