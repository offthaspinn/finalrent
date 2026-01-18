from typing import Optional

def mask_secret(s: Optional[str], keep: int = 4) -> str:
    if not s:
        return ""
    s = str(s)
    return "*" * max(len(s) - keep, 0) + s[-keep:]
