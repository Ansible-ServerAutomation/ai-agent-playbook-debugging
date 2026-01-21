from github import Github
from typing import List

class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.client = Github(token) if token else None

    def search_roles_in_org(self, org: str, query: str) -> List[dict]:
        if not self.client or not org:
            return []
        results = []
        organization = self.client.get_organization(org)
        for repo in organization.get_repos():
            try:
                contents = repo.get_contents("")
            except Exception:
                continue
            for content in contents:
                if content.path.endswith("roles") or "roles" in content.path:
                    results.append({"repo": repo.full_name, "path": content.path})
        return results

    def search_open_issues(self, owner: str, repo: str, title: str):
        if not self.client:
            return []
        repository = self.client.get_repo(f"{owner}/{repo}")
        issues = repository.get_issues(state="open")
        matches = []
        for issue in issues:
            if title.lower() in (issue.title or '').lower():
                matches.append({"number": issue.number, "title": issue.title, "html_url": issue.html_url})
        return matches

    def create_issue(self, owner: str, repo: str, title: str, body: str):
        if not self.client:
            return {}
        repository = self.client.get_repo(f"{owner}/{repo}")
        issue = repository.create_issue(title=title, body=body)
        return {"number": issue.number, "html_url": issue.html_url}
