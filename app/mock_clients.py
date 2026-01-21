"""Lightweight mock clients for demo/testing without external services."""
from typing import Dict

class MockGitHubClient:
    def __init__(self, token: str = None):
        self.token = token

    def search_open_issues(self, owner: str, repo: str, title: str):
        return []

    def create_issue(self, owner: str, repo: str, title: str, body: str) -> Dict:
        # return a fake issue structure
        return {"number": 1, "html_url": f"https://github.com/{owner}/{repo}/issues/1", "title": title}


class MockTeamsClient:
    def __init__(self, webhook_url: str = None):
        self.webhook = webhook_url

    def send_message(self, text: str):
        # For demo, just print or return True
        print("[MockTeams] send_message:", text)
        return True

    def send_adaptive_card(self, approval_id: int, title: str, owner: str, repo: str, host: str = None, port: str = None):
        card = {
            "approval_id": approval_id,
            "title": title,
            "repo": f"{owner}/{repo}",
            "approve_link": f"/approve_confirm?approval_id={approval_id}&action=approve",
            "deny_link": f"/approve_confirm?approval_id={approval_id}&action=deny",
        }
        print("[MockTeams] send_adaptive_card:", card)
        return card


class MockAWXClient:
    def __init__(self, base_url: str = None, token: str = None):
        self.base_url = base_url
        self.token = token

    def get_job_events(self, job_id: int):
        return {"job_id": job_id, "events": ["mock event 1", "mock event 2"]}
