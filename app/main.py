from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
from typing import Optional
import re
from pathlib import Path
import requests

from .ansible_analyzer import analyze_playbook_log
from .github_client import GitHubClient
from .teams_client import TeamsClient
from .awx_client import AWXClient
from .langchain_pipeline import LangChainPipeline
from .db import SessionLocal, init_db
from .models import PendingApproval
from .mock_clients import MockGitHubClient, MockTeamsClient, MockAWXClient
from fastapi.responses import HTMLResponse, PlainTextResponse
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
    # Load .env file into environment for convenience when running locally
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # don't overwrite already-exported env vars
                if k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass
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
    """Receive AWX webhook payload and enqueue processing in background.

    This endpoint acknowledges immediately to avoid timeouts from AWX. Detailed
    fetching/analysis happens in the background task `process_awx_job`.
    """
    payload = await request.json()
    job_id = payload.get("id") or (payload.get("job") and payload["job"].get("id")) or payload.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job id in payload")

    status = payload.get("status") or payload.get("job_status")

    # schedule background processing and respond quickly
    background_tasks.add_task(process_awx_job, job_id, status)
    return {"status": "accepted", "job_id": job_id}


def process_awx_job(job_id: int, status: Optional[str] = None):
    """Background worker: fetch job events, analyze, and notify Teams."""
    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))

    try:
        stdout = awx.get_job_stdout(job_id) or ""
    except Exception as e:
        stdout = ""

    # strip ANSI color/control sequences to make messages readable
    try:
        ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        stdout = ansi_re.sub("", stdout)
    except Exception:
        pass
    # Try to fetch job metadata for context (template name, project, etc.)
    job_meta = None
    try:
        job_meta = awx.get_job(job_id)
    except Exception:
        job_meta = None

    suggestions = []
    try:
        suggestions = analyze_playbook_log(stdout)
    except Exception:
        suggestions = []

    llm_summary = None
    llm_summary_text = None
    try:
        pipeline = LangChainPipeline()
        llm_summary = pipeline.summarize_log(stdout)
    except Exception as e:
        llm_summary = None
        # Friendly message for LLM failures
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        llm_summary_text = f"LLM unavailable: timeout contacting model at {ollama_url}. See logs for details."

    msg_lines = [f"AWX job {job_id} processed."]
    # include job metadata if available
    jt_name = None
    project_name = None
    job_status = status
    if job_meta:
        try:
            jt_name = job_meta.get("summary_fields", {}).get("job_template", {}).get("name") or (job_meta.get("job_template") and job_meta.get("job_template").get("name"))
        except Exception:
            jt_name = None
        try:
            project_name = job_meta.get("summary_fields", {}).get("project", {}).get("name")
        except Exception:
            project_name = None
        if not job_status:
            job_status = job_meta.get("status")

    # Header
    header_lines = ["AWX Job Notification"]
    if jt_name:
        header_lines.append(f"Template: {jt_name}")
    if project_name:
        header_lines.append(f"Project: {project_name}")
    header_lines.append(f"Job ID: {job_id}")
    header_lines.append(f"Status: {job_status or 'unknown'}")
    msg_lines = header_lines
    # If job is still running, skip notifying to avoid noisy updates
    computed_status = (job_status or "").lower()
    if computed_status in ("running", "pending", "waiting"):
        return
    # Build a short suggestions summary based on status and analyzer output
    suggestions_summary = None
    if not suggestions:
        if (job_status or "").lower() in ("successful", "ok", "finished"):
            suggestions_summary = "No improvements detected."
        else:
            suggestions_summary = "No concrete matches from quick analyzer; consider investigating failures and re-running with -vvv."
    else:
        # If analyzer returned structured value, extract advice
        if isinstance(suggestions, dict):
            advice = suggestions.get("advice") or suggestions.get("message") or None
            match = suggestions.get("match")
            context = suggestions.get("context")
            parts = []
            if advice:
                parts.append(f"Advice: {advice}")
            if match is not None:
                parts.append(f"Match: {match}")
            if context:
                parts.append(f"Context: {context}")
            suggestions_summary = "; ".join(parts) if parts else str(suggestions)
        elif isinstance(suggestions, list):
            normalized = []
            for x in suggestions[:5]:
                if isinstance(x, dict):
                    normalized.append(x.get("advice") or x.get("message") or str(x))
                else:
                    normalized.append(str(x))
            suggestions_summary = "; ".join(normalized)
        else:
            suggestions_summary = str(suggestions)

    if suggestions_summary:
        msg_lines.append("")
        msg_lines.append("Suggestions (quick analyzer):")
        msg_lines.append(f" - {suggestions_summary}")
    # Prefer a cleaned text summary if available
    if llm_summary_text:
        msg_lines.append("")
        msg_lines.append("LLM summary:")
        msg_lines.append(f" - {llm_summary_text}")
    elif llm_summary:
        msg_lines.append("")
        msg_lines.append("LLM summary:")
        # If LLM returned structured summary, format it
        if isinstance(llm_summary, dict):
            summary_text = llm_summary.get("summary") or llm_summary.get("text") or None
            remediations = llm_summary.get("remediations") or llm_summary.get("fixes") or []
            enhancements = llm_summary.get("enhancements") or []
            if summary_text:
                msg_lines.append(f" - Summary: {summary_text}")
            if remediations:
                if isinstance(remediations, list):
                    msg_lines.append(" - Remediations:")
                    for r in remediations:
                        msg_lines.append(f"    - {r}")
                else:
                    msg_lines.append(f" - Remediations: {remediations}")
            if enhancements:
                msg_lines.append(" - Enhancements:")
                for e in enhancements:
                    msg_lines.append(f"    - {e}")
        else:
            msg_lines.append(str(llm_summary))
    # Provide a short inline snippet and a link to view full output to avoid Teams truncation
    # Precompute agent stdout URL (fallback) so we always have a link
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = os.getenv("APP_PORT", "8000")
    scheme = "https" if os.getenv("APP_HTTPS", "false").lower() in ("1", "true", "yes") else "http"
    agent_stdout_url = f"{scheme}://{host}:{port}/awx/jobs/{job_id}/stdout"
    full_url = agent_stdout_url

    if stdout:
        inline_snippet = (stdout[:800] + "...") if len(stdout) > 800 else stdout
        msg_lines.append("")
        msg_lines.append("Output (truncated):")
        msg_lines.append(inline_snippet)
        # construct a link to view full output on AWX tower UI if possible, otherwise fall back to agent endpoint
        awx_url = os.getenv("AWX_URL")
        full_awx_url = None
        try:
            if awx_url:
                full_awx_url = awx_url.rstrip('/') + f"/#/jobs/{job_id}/output"
        except Exception:
            full_awx_url = None
        full_url = full_awx_url or agent_stdout_url
        msg_lines.append("")
        msg_lines.append(f"View full output: {full_url}")

    # Prepare a link to open a GH issue via the agent (server-side creation)
    create_issue_url = f"{scheme}://{host}:{port}/issues/open_from_job?job_id={job_id}"

    message = "\n\n".join(msg_lines)
    # Send as Adaptive Card if possible
    try:
        teams.send_awx_notification_card(jt_name, project_name, job_id, job_status or status, suggestions_summary, (llm_summary if isinstance(llm_summary, str) else (llm_summary.get('summary') if isinstance(llm_summary, dict) else str(llm_summary))) if llm_summary else None, full_url, approve_url=None, create_issue_url=create_issue_url)
    except Exception as e:
        try:
            print(f"teams.send_awx_notification_card failed: {e}")
        except Exception:
            pass


@app.get("/github/roles_search")
def github_roles_search(q: str):
    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    results = gh.search_roles_in_org(os.getenv("GITHUB_ORG"), q)
    return {"matches": results}


@app.get("/awx/jobs/{job_id}/stdout", response_class=PlainTextResponse)
def awx_job_stdout(job_id: int):
    """Return full assembled job stdout as plain text for viewing or download."""
    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    try:
        stdout = awx.get_job_stdout(job_id)
    except Exception:
        stdout = None
    if not stdout:
        raise HTTPException(status_code=404, detail="Job stdout not found")
    return stdout


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


@app.get("/issues/open")
def issues_open(pending_id: int):
    """Create a GitHub issue for the given pending approval and return a simple page.

    This endpoint is intended to be opened from the Adaptive Card 'Open GH issue' button.
    """
    db = SessionLocal()
    pending = db.query(PendingApproval).filter(PendingApproval.id == pending_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending approval not found")

    # attempt to derive job id from title (we set titles as 'AWX job {id} suggestions: ...')
    import re as _re
    m = _re.search(r"AWX job (\d+)", pending.title or "")
    job_id = int(m.group(1)) if m else None

    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    stdout = None
    if job_id:
        try:
            stdout = awx.get_job_stdout(job_id)
        except Exception:
            stdout = None

    issue_body = (pending.body or "")
    if stdout:
        issue_body = issue_body + "\n\n---\n\nFull job output:\n" + stdout

    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    try:
        issue = gh.create_issue(pending.owner, pending.repo, pending.title, issue_body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create GitHub issue: {e}")

    try:
        pending.status = "issue_created"
        db.commit()
    except Exception:
        pass

    # notify via Teams that issue was created
    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))
    try:
        teams.send_message(f"Created GitHub issue: {issue.get('html_url')}")
    except Exception:
        pass

    return {"status": "created", "issue": issue}


@app.get("/issues/open_from_job")
def issues_open_from_job(job_id: int):
    """Create a GitHub issue for the given AWX job id using job metadata and stdout."""
    awx = AWXClient(os.getenv("AWX_URL"), os.getenv("AWX_TOKEN"))
    job_meta = awx.get_job(job_id)
    stdout = awx.get_job_stdout(job_id) or ""

    # try to infer GH owner/repo from project SCM
    gh_owner = None
    gh_repo_name = None
    try:
        proj = job_meta.get("summary_fields", {}).get("project") if job_meta else None
        if isinstance(proj, dict):
            scm = proj.get("scm_url") or proj.get("scm")
            if scm and "github.com" in scm:
                import re as _re
                m = _re.search(r"[:/](?P<owner>[-\w]+)/(?P<repo>[-\w]+)(?:\.git)?$", scm)
                if m:
                    gh_owner = m.group("owner")
                    gh_repo_name = m.group("repo")
    except Exception:
        gh_owner = None
        gh_repo_name = None

    owner = gh_owner or os.getenv("GITHUB_ORG")
    repo = gh_repo_name or os.getenv("GITHUB_REPO") or os.getenv("GITHUB_DEFAULT_REPO")
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Could not determine GitHub owner/repo for this project. Set GITHUB_REPO or ensure project SCM is a GitHub URL.")

    title = f"AWX job {job_id} ({job_meta.get('name') if job_meta else job_id}) investigation"
    body = f"AWX job {job_id} reported status: {job_meta.get('status') if job_meta else 'unknown'}.\n\nJob metadata:\n{job_meta}\n\nFull stdout:\n{stdout}"

    gh = GitHubClient(os.getenv("GITHUB_TOKEN"))
    try:
        issue = gh.create_issue(owner, repo, title, body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create GitHub issue: {e}")

    teams = TeamsClient(os.getenv("TEAMS_WEBHOOK_URL"))
    try:
        teams.send_message(f"Created GitHub issue: {issue.get('html_url')}")
    except Exception:
        pass

    return {"status": "created", "issue": issue}


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
        try:
            issue = gh.create_issue(approval.owner, approval.repo, approval.title, approval.body)
            approval.status = "approved"
            db.commit()
            # prefer adaptive card or simple message
            teams.send_message(f"Issue created: {issue.get('html_url')}")
            return {"status": "approved", "issue": issue}
        except Exception as e:
            try:
                approval.status = "error"
                db.commit()
            except Exception:
                pass
            try:
                teams.send_message(f"Failed to create issue for approval {approval_id}: {e}")
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to create issue: {e}")

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

