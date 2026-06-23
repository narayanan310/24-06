"""
intent_validator.py
Post-SLM semantic safety validator.

The SLM can hallucinate inverted commands — it receives "close androof"
and returns SET_POSITION=100 (open). This module catches that contradiction
BEFORE the intent reaches the CAN bus.

Architecture:
    Regex → Context → SLM → [IntentValidator] → CAN
                              ^^^^^^^^^^^^^^^^^^^
                              This module lives here
"""

import re

# ── Semantic polarity keywords ────────────────────────────────────────────────
# Words that strongly indicate a CLOSING / REDUCING / OFF intent in the user input.
_CLOSING_WORDS  = {"close", "shut", "seal", "lock", "down", "off", "lower",
                   "decrease", "reduce", "stop", "disable", "deactivate"}
_OPENING_WORDS  = {"open", "up", "on", "raise", "increase", "start",
                   "enable", "activate", "higher", "more"}

# ── Commands whose value polarity can be validated ────────────────────────────
# Maps command → (low_value, high_value) so we know which direction is "open"
_COMMAND_POLARITY: dict[str, tuple[int, int]] = {
    "SET_POSITION":   (0, 100),   # 0=closed, 100=open
    "SET_HEADLIGHTS": (0, 1),     # 0=off, 1=on
    "TOGGLE_AC":      (0, 1),     # 0=off, 1=on
    "SET_FAN_SPEED":  (1, 5),     # 1=low, 5=high
    "SET_TEMPERATURE": (17, 29),  # lower=cooler, higher=warmer
    "SET_BRIGHTNESS": (0, 100),   # 0=dark, 100=bright
}

# ── Commands with risky high values requiring confirmation ────────────────────
_RISKY_COMMANDS: set[tuple] = {
    ("SET_POSITION",   100),   # fully open sunroof
    ("SET_FAN_SPEED",  5),     # max fan
    ("SET_TEMPERATURE", 29),   # max heat
    ("SET_TEMPERATURE", 17),   # max cold
}

# ── Confirmation-required commands (from macros or direct) ────────────────────
_REQUIRES_CONFIRM_COMMANDS = {"MACRO_RESET", "DOG_MODE_MACRO"}


def _user_intent_direction(text: str) -> str | None:
    """
    Returns 'close' if the user clearly wanted to close/reduce/off,
    'open' if the user clearly wanted to open/raise/on,
    or None if ambiguous.
    """
    words = set(text.lower().split())
    has_close = bool(words & _CLOSING_WORDS)
    has_open  = bool(words & _OPENING_WORDS)
    if has_close and not has_open:
        return "close"
    if has_open and not has_close:
        return "open"
    return None


def validate(user_text: str, intent: dict) -> tuple[bool, str | None]:
    """
    Validate that the resolved intent is semantically consistent
    with what the user actually said.

    Returns:
        (is_valid, rejection_reason)
        - (True,  None)   → intent is safe to dispatch
        - (False, reason) → intent should be rejected and reason spoken to user
    """
    if intent is None:
        return True, None

    cmd   = intent.get("command", "")
    value = intent.get("value")

    if cmd not in _COMMAND_POLARITY or value is None:
        return True, None

    lo, hi = _COMMAND_POLARITY[cmd]
    user_dir = _user_intent_direction(user_text)

    if user_dir is None:
        return True, None  # ambiguous — let it through

    # Determine polarity of the resolved value
    # "close" direction = low value, "open" direction = high value
    midpoint = (lo + hi) / 2
    intent_dir = "open" if value > midpoint else "close"

    if user_dir != intent_dir:
        # Contradiction detected!
        if cmd == "SET_POSITION":
            wanted   = "close the sunroof"   if user_dir == "close" else "open the sunroof"
            got      = "open it"             if intent_dir == "open" else "close it"
        elif cmd == "TOGGLE_AC":
            wanted   = "turn AC off"   if user_dir == "close" else "turn AC on"
            got      = "turn it on"    if intent_dir == "open" else "turn it off"
        elif cmd == "SET_HEADLIGHTS":
            wanted   = "turn lights off" if user_dir == "close" else "turn lights on"
            got      = "turn them on"    if intent_dir == "open" else "turn them off"
        elif cmd == "SET_FAN_SPEED":
            wanted   = "lower the fan"   if user_dir == "close" else "raise the fan"
            got      = "raise it"        if intent_dir == "open" else "lower it"
        else:
            wanted = f"a {user_dir} action"
            got    = f"a {intent_dir} action"

        reason = (
            f"I heard you wanted to {wanted}, but the AI resolved it to {got}. "
            f"Blocking for safety. Please repeat your command."
        )
        print(f"[Validator] BLOCKED: user said '{user_dir}' but SLM resolved to '{intent_dir}' "
              f"for {cmd}={value}")
        return False, reason

    return True, None


def requires_confirmation(intent: dict) -> bool:
    """
    Returns True if this intent requires verbal confirmation before executing.
    Used for high-risk / irreversible commands.
    """
    cmd   = intent.get("command", "")
    value = intent.get("value")

    # Macro resets always need confirmation
    if cmd in _REQUIRES_CONFIRM_COMMANDS:
        return True

    # Specific high-risk (command, value) pairs
    if (cmd, value) in _RISKY_COMMANDS:
        return True

    return False


def confirmation_prompt(intent: dict) -> str:
    """Generate a natural confirmation question for a risky intent."""
    cmd   = intent.get("command", "")
    value = intent.get("value")

    if cmd == "SET_POSITION" and value == 100:
        return "Open the sunroof fully? Say yes to confirm."
    if cmd == "SET_FAN_SPEED" and value == 5:
        return "Set fan to maximum speed? Say yes to confirm."
    if cmd == "SET_TEMPERATURE" and value == 29:
        return "Set temperature to maximum 29 degrees? Say yes to confirm."
    if cmd == "SET_TEMPERATURE" and value == 17:
        return "Set temperature to minimum 17 degrees? Say yes to confirm."
    if cmd == "MACRO_RESET":
        return "This will reset all systems to defaults. Say yes to confirm."
    return "Confirm this action? Say yes to proceed."
