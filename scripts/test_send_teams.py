import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.teams_client import TeamsClient
import os
# simple .env parser in case python-dotenv is not installed
def read_env(path='.env'):
    if not os.path.exists(path):
        return {}
    res={}
    with open(path,'r',encoding='utf8') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k,v=line.split('=',1)
            res[k.strip()]=v.strip()
    return res

env=read_env()
u=env.get('TEAMS_WEBHOOK_URL') or os.getenv('TEAMS_WEBHOOK_URL')
print("webhook:", (u[:80] + "...") if u else None)
cli = TeamsClient(u)
try:
    ok = cli.send_message("agent test message direct from TeamsClient")
    print("send_message returned:", ok)
except Exception as e:
    print("exception:", type(e).__name__, e)
