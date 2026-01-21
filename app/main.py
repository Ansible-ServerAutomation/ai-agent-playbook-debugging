from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
from typing import Optional

from .ansible_analyzer import analyze_playbook_log
from .github_client import GitHubClient
from .teams_client import TeamsClient
from .awx_client import AWXClient
from .langchain_pipeline import LangChainPipeline
from .db import SessionLocal, init_db
from .models import PendingApproval
from .mock_clients import MockGitHubClient, MockTeamsClient, MockAWXClient
from fastapi.responses import HTMLResponse
import os
from .security import verify_sig
from fastapi.templating import Jinja2Templates
from fastapi import Request

templates = Jinja2Templates(directory="templates")

app = FastAPI(title="Ansible Debug Agent")

class LogRequest(BaseModel):
    source: str
    log: str

class IssueRequest(BaseModel):
    owner: str
    repo: str
    title: str
    body: str
    create_if_missing: Optional[bool] = False


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze_log")
def analyze_log(req: LogRequest):
    # Use quick analyzer first
    suggestions = analyze_playbook_log(req.log)
    # Also prepare an LLM summary in background (non-blocking)
    try:
        pipeline = LangChainPipeline()
        summary = pipeline.summarize_log(req.log)
    except Exception:
        summary = None
    return {"source": req.source, "suggestions": suggestions, "llm_summary": summary}


@app.get("/awx/jobs/{job_id}")
def get_awx_job(job_id: int):
    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    job = awx.get_job_events(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/awx/webhook")
async def awx_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive AWX webhook payloads, assemble job stdout, run analyzer/LLM, and notify Teams.

    Expected AWX webhook JSON should include at least one of: `id`, `job.id`, or `job_id`.
    If `status` is present we'll include it in the notification.
    """
    payload = await request.json()
    # extract job id from common locations
    job_id = payload.get("id") or (payload.get("job") and payload["job"].get("id")) or payload.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job id in payload")

    status = payload.get("status") or payload.get("job_status")

    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))

    # assemble stdout
    stdout = awx.get_job_stdout(job_id) or ""

    # quick analyzer
    suggestions = analyze_playbook_log(stdout)

    # LLM summary (best-effort, non-blocking)
    try:
        pipeline = LangChainPipeline()
        llm_summary = pipeline.summarize_log(stdout)
    except Exception:
        llm_summary = None

    # build message
    msg_lines = [f"AWX job {job_id} webhook received."]
    if status:
        msg_lines.append(f"Status: {status}")
    if suggestions:
        msg_lines.append("Suggestions (quick analyzer):")
        msg_lines.extend(suggestions if isinstance(suggestions, list) else [suggestions])
    if llm_summary:
        msg_lines.append("LLM summary:")
        msg_lines.append(llm_summary)
    if stdout:
        msg_lines.append("Truncated job stdout:")
        msg_lines.append(stdout[:2000])  # avoid huge payloads

    message = "\n\n".join(msg_lines)
    background_tasks.add_task(teams.send_message, message)

    return {"status": "ok", "job_id": job_id}


@app.get("/github/roles_search")
def github_roles_search(q: str):
    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    results = gh.search_roles_in_org(os.getenv("GITHUB_ORG"), q)
    return {"matches": results}


@app.post("/issues/check_and_maybe_create")
def check_and_create_issue(req: IssueRequest, background_tasks: BackgroundTasks):
    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))

    open_issues = gh.search_open_issues(req.owner, req.repo, req.title)
    if open_issues:
        teams.send_message(f"Found existing open issue(s) for '{req.title}': {len(open_issues)}")
        return {"status": "exists", "count": len(open_issues), "issues": open_issues}

    # If caller requested immediate creation
    if req.create_if_missing:
        new_issue = gh.create_issue(req.owner, req.repo, req.title, req.body)
        teams.send_message(f"Created issue: {new_issue.get('html_url')}")
        return {"status": "created", "issue": new_issue}

    # Otherwise create a pending approval record and send Teams Adaptive Card requesting approval
    db = SessionLocal()
    pending = PendingApproval(owner=req.owner, repo=req.repo, title=req.title, body=req.body)
    db.add(pending)
    db.commit()
    db.refresh(pending)
    # Send an Adaptive Card with Approve/Deny links back to this service
    background_tasks.add_task(teams.send_adaptive_card, pending.id, pending.title, pending.owner, pending.repo)
    return {"status": "pending", "approval_id": pending.id}


@app.post("/teams/approval_callback")
def teams_approval_callback(approval_id: int, action: str):
    """Receive approval/deny actions from Teams (or other webhook) and act accordingly.
    Expected JSON: {"approval_id": 123, "action": "approve"}
    """
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))
    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    db = SessionLocal()
    approval = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if action.lower() == "approve":
        issue = gh.create_issue(approval.owner, approval.repo, approval.title, approval.body)
        approval.status = "approved"
        db.commit()
        teams.send_message(f"Issue created: {issue.get('html_url')}")
        return {"status": "approved", "issue": issue}

    approval.status = "denied"
    db.commit()
    teams.send_message(f"Approval {approval_id} was denied.")
    return {"status": "denied"}


@app.get("/approve")
def approve_get(approval_id: int, action: str, sig: str = None):
    """Handle approval clicks from Adaptive Card buttons (simple GET link callbacks).

    If `APP_SIGNING_SECRET` is set, require a valid `sig` parameter.
    """
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))
    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    db = SessionLocal()
    approval = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    secret = os.getenv("APP_SIGNING_SECRET")
    if secret:
        if not sig or not verify_sig(secret, approval_id, action, sig):
            raise HTTPException(status_code=403, detail="Invalid or missing signature")

    if action.lower() == "approve":
        issue = gh.create_issue(approval.owner, approval.repo, approval.title, approval.body)
        approval.status = "approved"
        db.commit()
        teams.send_message(f"Issue created: {issue.get('html_url')}")
        return {"status": "approved", "issue": issue}

    approval.status = "denied"
    db.commit()
    teams.send_message(f"Approval {approval_id} was denied.")
    return {"status": "denied"}


@app.get("/approve_confirm", response_class=HTMLResponse)
def approve_confirm_page(request: Request, approval_id: int, action: str, sig: str = None):
        """Render an approval confirmation HTML page with action buttons.

        If `APP_SIGNING_SECRET` is set, require `sig` and validate it.
        """
        secret = os.getenv("APP_SIGNING_SECRET")
        if secret:
                if not sig or not verify_sig(secret, approval_id, action, sig):
                        raise HTTPException(status_code=403, detail="Invalid or missing signature")
        # Render template with forms carrying the signature forward
        return templates.TemplateResponse("approve.html", {"request": request, "approval_id": approval_id, "action": action, "sig": sig})


@app.post("/demo/mock_e2e")
def demo_mock_e2e():
        """Create a pending approval using mock clients and return mock card payload.

        This demonstrates the flow without external services.
        """
        db = SessionLocal()
        # create a pending approval record
        pending = PendingApproval(owner="mock_owner", repo="mock_repo", title="Mock E2E Issue", body="Mock body")
        db.add(pending)
        db.commit()
        db.refresh(pending)

        # create mock teams card
        mock_teams = MockTeamsClient()
        card = mock_teams.send_adaptive_card(pending.id, pending.title, pending.owner, pending.repo)
        return {"status": "pending", "approval_id": pending.id, "card": card}

