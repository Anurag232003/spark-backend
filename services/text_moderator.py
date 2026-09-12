# backend/services/text_moderator.py
import re
from typing import Tuple

VULGAR_PATTERNS = [
    # English Profanity & Harassment
    r"\bf+u+c+k",
    r"\bb+i+t+c+h",
    r"\bd+i+c+k",
    r"\bp+u+s+s+y",
    r"\bw+h+o+r+e",
    r"\bs+l+u+t",
    r"\ba+s+s+h+o+l+e",
    r"\bb+a+s+t+a+r+d",
    r"\bc+u+n+t",
    r"\bs+e+n+d+\s*n+u+d+e",
    r"\bn+u+d+e",
    r"\br+a+p+e",
    r"\bb+o+o+b",
    r"\bn+a+k+e+d",
    r"\bb+l+o+w+j+o+b",

    # Hindi / Hinglish Abusive & Vulgar Terms
    r"\bm+a+d+a+r+c+h+o",
    r"\bm+c\b",
    r"\bb[eah]+n+c+h+o",
    r"\bb+c\b",
    r"\bc+h+u+t+i+y",
    r"\bc+h+u+t\b",
    r"\bb+h+o+s+[dt]",
    r"\bg+a+a?n+[dt]",
    r"\bl+u+n+[dt]",
    r"\bl+a+w+[dt]",
    r"\br+a+n+[dt]",
    r"\bh+a+r+a+m",
    r"\bk+a+m+i+n",
    r"\bs+u+a+r",
    r"\bc+h+u+m+m+a",
    r"\bj+h+a+a?n+[dt]",
    r"\bt+a+t+t+e",
    r"\bm+u+t+h",
    r"\bc+h+o+[dt]\b",
    r"\bc+h+u+[dt]",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in VULGAR_PATTERNS]

def is_message_clean(text: str) -> Tuple[bool, str]:
    """
    Scans text for vulgarity, abusive slurs, or sexual solicitation.
    Returns (is_clean, reason).
    """
    if not text:
        return True, ""

    normalized = (
        text.lower()
        .replace("@", "a").replace("4", "a")
        .replace("!", "i").replace("1", "i").replace("|", "i")
        .replace("$", "s").replace("5", "s")
        .replace("0", "o")
        .replace("3", "e")
        .replace("*", "").replace("_", "").replace("~", "")
    )

    for pattern in COMPILED_PATTERNS:
        if pattern.search(normalized) or pattern.search(text):
            return False, "Message rejected: Vulgar, abusive, or sexually explicit language is not allowed on Spark."

    return True, ""
