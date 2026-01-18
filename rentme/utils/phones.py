import re
from typing import Optional

def normalize_msisdn(phone: Optional[str]) -> str:
    if not phone:
        return ""

    s = re.sub(r"\D", "", str(phone))

    if s.startswith("0") and len(s) == 10:
        s = "254" + s[1:]
    elif s.startswith("7") and len(s) == 9:
        s = "254" + s
    elif s.startswith("254") and len(s) == 12:
        pass
    else:
        return ""

    return s if re.fullmatch(r"2547\d{8}", s) else ""

