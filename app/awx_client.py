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
