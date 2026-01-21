
import requests
import os


class TeamsClient:
    def __init__(self, webhook_url: str):
        self.webhook = webhook_url

    def send_message(self, text: str):
        if not self.webhook:
            return False
        payload = {"text": text}
        resp = requests.post(self.webhook, json=payload, timeout=10)
        return resp.status_code == 200 or resp.status_code == 201

    def send_adaptive_card(self, approval_id: int, title: str, owner: str, repo: str, host: str = None, port: str = None):
        """Send an Adaptive Card with Approve/Deny buttons linking back to this service."""
        if not self.webhook:
            return False
        host = host or os.getenv("APP_HOST", "localhost")
        port = port or os.getenv("APP_PORT", "8000")
        # link into an HTML confirmation page which provides a nicer UX for approvals
        from .security import generate_sig
        secret = os.getenv("APP_SIGNING_SECRET")
        if secret:
            sig_a = generate_sig(secret, approval_id, "approve")
            sig_d = generate_sig(secret, approval_id, "deny")
            approve_url = f"http://{host}:{port}/approve_confirm?approval_id={approval_id}&action=approve&sig={sig_a}"
            deny_url = f"http://{host}:{port}/approve_confirm?approval_id={approval_id}&action=deny&sig={sig_d}"
        else:
            approve_url = f"http://{host}:{port}/approve_confirm?approval_id={approval_id}&action=approve"
            deny_url = f"http://{host}:{port}/approve_confirm?approval_id={approval_id}&action=deny"

        card_content = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": f"Approval requested: {title}"},
                {"type": "TextBlock", "text": f"Repository: {owner}/{repo}"},
                {"type": "TextBlock", "text": f"Approval ID: {approval_id}"}
            ],
            "actions": [
                {"type": "Action.OpenUrl", "title": "Approve", "url": approve_url},
                {"type": "Action.OpenUrl", "title": "Deny", "url": deny_url}
            ]
        }

        payload = {
            "type": "message",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": card_content}
            ]
        }
        try:
            resp = requests.post(self.webhook, json=payload, timeout=10)
            return resp.status_code in (200, 201)
        except Exception:
            return False

