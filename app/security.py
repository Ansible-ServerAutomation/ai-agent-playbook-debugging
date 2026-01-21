import hmac
import hashlib

def generate_sig(secret: str, approval_id: int, action: str) -> str:
    """Generate HMAC-SHA256 hex signature for approval link."""
    msg = f"{approval_id}:{action}".encode("utf-8")
    key = secret.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

def verify_sig(secret: str, approval_id: int, action: str, sig: str) -> bool:
    if not sig:
        return False
    expected = generate_sig(secret, approval_id, action)
    return hmac.compare_digest(expected, sig)
