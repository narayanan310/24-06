"""
intent_splitter.py
Splits compound driver commands into individual clauses.

IMPORTANT: Only split on EXPLICIT sequential conjunctions.
Do NOT split on commas or periods — STT creates weird punctuation and
commas inside descriptions (e.g. "big, red button") would be destroyed.

Examples
--------
"Open the sunroof and then turn on the headlights"
    -> ["Open the sunroof", "turn on the headlights"]

"Make it cooler then dim the lights"
    -> ["Make it cooler", "dim the lights"]

"I'm freezing, turn up the heat"
    -> ["I'm freezing, turn up the heat"]   <-- kept whole, comma ignored
"""

import re


# Only split on clear sequential conjunctions — never on commas or periods.
# "and" alone is too risky ("nice and warm" would split wrong).
_SPLIT_RE = re.compile(
    r'\s+and\s+then\s+'
    r'|\s+and\s+also\s+'
    r'|\s+after\s+that\s+'
    r'|\s+then\s+also\s+',
    flags=re.IGNORECASE,
)

_MIN_LEN = 4   # ignore fragments shorter than this


def split_intents(text: str) -> list[str]:
    """
    Returns a list of individual command strings.
    Always returns at least one element (the original text).
    Defaults to NOT splitting if the result would be meaningless fragments.
    """
    parts = _SPLIT_RE.split(text.strip())

    # Clean up whitespace and remove short fragments
    clauses = [p.strip() for p in parts if len(p.strip()) >= _MIN_LEN]

    # Extra safety: if any split piece is missing a verb, keep original
    # (e.g. "open, open, and roof" -> don't split, pass full string)
    if len(clauses) > 1:
        _VERBS = {
            "set", "open", "close", "turn", "make", "increase",
            "decrease", "raise", "lower", "switch", "put", "keep",
        }
        if not all(any(v in c.lower() for v in _VERBS) for c in clauses):
            return [text.strip()]

    return clauses if clauses else [text.strip()]
