from .langchain_agent import OllamaModel
from .prompts import LOG_SUMMARY_PROMPT, ISSUE_CREATION_PROMPT
import json

class LangChainPipeline:
    def __init__(self, ollama_url=None):
        self.ollama = OllamaModel(ollama_url)

    def summarize_log(self, log_text: str):
        prompt = LOG_SUMMARY_PROMPT.format(log=log_text)
        resp = self.ollama.ask(prompt, model="mistral")
        # Try to parse JSON response
        try:
            parsed = json.loads(resp)
            return parsed
        except Exception:
            # fallback: return plain text under summary
            return {"summary": resp, "remediations": [], "enhancements": []}

    def draft_issue(self, title: str, context: str):
        prompt = ISSUE_CREATION_PROMPT.format(title=title, context=context)
        resp = self.ollama.ask(prompt, model="mistral")
        return resp
