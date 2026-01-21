LOG_SUMMARY_PROMPT = """
You are an expert Ansible engineer. Given the following Ansible job log, provide:
1) A concise summary of the failure.
2) Up to 3 targeted remediation suggestions (code-level where possible).
3) Suggestions for role enhancements or automation improvements.

Log:
{log}

Respond in JSON with keys: summary, remediations, enhancements.
"""

ISSUE_CREATION_PROMPT = """
You are an assistant that drafts a clear GitHub issue body for an Ansible role bug fix.
Title: {title}
Context/Logs:
{context}

Produce a markdown-formatted issue body describing the bug, steps to reproduce, expected behavior, observed behavior, and suggested fix.
"""
