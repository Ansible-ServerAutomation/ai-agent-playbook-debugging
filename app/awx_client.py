import requests

class AWXClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/') if base_url else None
        self.token = token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get_job_events(self, job_id: int):
        if not self.base_url:
            return None
        url = f"{self.base_url}/api/v2/jobs/{job_id}/job_events/"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json()

    def get_job_stdout(self, job_id: int):
        """Assemble human-readable stdout from AWX job events."""
        events = self.get_job_events(job_id)
        if not events:
            return None
        parts = []
        for ev in events.get("results", []):
            stdout = ev.get("stdout")
            if not stdout:
                stdout_lines = ev.get("stdout_lines")
                if isinstance(stdout_lines, list):
                    stdout = "\n".join(stdout_lines)
            if not stdout:
                continue
            host = ev.get("host") or ev.get("play", "") or ""
            event = ev.get("event") or ev.get("event_display") or ""
            prefix = f"[{event}]" if event else ""
            header = f"{prefix} {host}: " if host or prefix else ""
            parts.append(f"{header}{stdout}")
        if not parts:
            return None
        return "\n".join(parts)
