import re

COMMON_ERRORS = [
    (re.compile(r"FAILED! => .*"), "Task failed — check module parameters and target host state."),
    (re.compile(r"ERROR! .*"), "Ansible error — check playbook syntax and variables."),
    (re.compile(r"UNREACHABLE! .*"), "Host unreachable — check inventory and SSH connectivity."),
    (re.compile(r"permission denied", re.I), "Permission denied — check remote user and privileges."),
]

def analyze_playbook_log(log_text: str):
    """Simple analyzer that scans logs for common patterns and returns suggestions."""
    suggestions = []
    lines = log_text.splitlines()
    for i, line in enumerate(lines[-200:]):
        for pattern, message in COMMON_ERRORS:
            if pattern.search(line):
                context = "\n".join(lines[max(0, i-3):i+3])
                suggestions.append({"match": line.strip(), "advice": message, "context": context})
    # If no suggestions, provide a generic hint for further analysis
    if not suggestions:
        suggestions.append({"match": None, "advice": "No clear pattern matched. Consider running with increased verbosity (-vvv) or uploading full job events.", "context": None})
    return suggestions
