"""
safety_supervisor.py
Safety gate between intent resolution and CAN bus dispatch.

Responsibilities
────────────────
• Hard-block commands outside safe operating ranges.
• Warn (but allow) state-conflicting commands.
• Block explicitly banned commands.
• Dynamic policies based on live vehicle state:
    - Sunroof blocked above SUNROOF_SPEED_LIMIT km/h.
    - Sunroof blocked when raining.
    - Headlights forced ON warning above HEADLIGHT_SPEED_THRESHOLD km/h at night.
    - Extreme temperature guard at high speed (AC workload warning).
• Gibberish / nonsense input detection (standalone utility).
"""

import re


# ── Static safe ranges ────────────────────────────────────────────────────────

_SAFE_RANGES: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1, 5),
    "SET_POSITION":    (0, 100),
    "SET_BRIGHTNESS":  (0, 100),
    "SET_HEADLIGHTS":  (0, 1),
    "TOGGLE_AC":       (0, 1),
}

# Dynamically populated (e.g. during emergency / valet mode)
_BLOCKED_COMMANDS: set[str] = set()

# ── Dynamic policy thresholds ─────────────────────────────────────────────────
SUNROOF_SPEED_LIMIT       = 100   # km/h — hard-block sunroof opening above this
HEADLIGHT_SPEED_THRESHOLD =  80   # km/h — warn if headlights are off at high speed
TEMP_HIGH_SPEED_WARN      = 120   # km/h — warn about extreme temps at speed


class SafetySupervisor:
    def __init__(self, state_manager) -> None:
        self.sm = state_manager

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, intent: dict) -> tuple[bool, str | None]:
        """
        Returns (allowed: bool, message: str | None).
        (False, msg) → block — do NOT dispatch to CAN bus.
        (True,  msg) → allow but surface warning.
        (True, None) → clean pass.
        """
        cmd = intent.get("command")
        val = intent.get("value")

        # Non-vehicle / informational intents always pass
        if cmd in (None, "UNKNOWN", "SAFETY_ALERT", "RAG_RESPONSE",
                   "STATUS_QUERY", "MACRO_RESET", "INCOMPLETE_COMMAND"):
            return True, None

        # ── Explicitly blocked commands ───────────────────────────────────────
        if cmd in _BLOCKED_COMMANDS:
            return False, f"[Safety] {cmd} is currently blocked."

        # ── Static range check ────────────────────────────────────────────────
        if cmd in _SAFE_RANGES and val is not None:
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                return False, f"[Safety] Non-numeric value '{val}' for {cmd} — blocked."
            lo, hi = _SAFE_RANGES[cmd]
            if not (lo <= v <= hi):
                return False, (
                    f"[Safety] {cmd} value {v} is outside safe range "
                    f"[{lo}–{hi}]. Command blocked."
                )

        # ── Dynamic state-based policies ──────────────────────────────────────
        state = self.sm.get_state()
        speed     = state.get("vehicle_speed", 0)   # km/h, 0 if unknown
        is_raining = state.get("is_raining", False)

        # Policy 1: Sunroof – hard-block above speed limit or in rain
        if cmd == "SET_POSITION":
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                v = 0

            if v > 0:
                if speed >= SUNROOF_SPEED_LIMIT:
                    return False, (
                        f"[Safety] Sunroof opening blocked — vehicle speed {speed} km/h "
                        f"exceeds limit of {SUNROOF_SPEED_LIMIT} km/h."
                    )
                if is_raining:
                    return False, (
                        "[Safety] Sunroof opening blocked — rain detected. "
                        "Close the sunroof to avoid water ingress."
                    )
                # Efficiency warning
                if state.get("ac_enabled", False):
                    return True, (
                        "Opening sunroof while AC is running. "
                        "Consider turning off AC to save energy."
                    )

            if v == 0:
                if state.get("sunroof_position", 0) == 0:
                    return True, None   # already closed — idempotent
                return True, "Closing sunroof. Please ensure hands and objects are clear."

        # Policy 2: Headlights – warn if turning off at high speed (e.g. night)
        if cmd == "SET_HEADLIGHTS" and val == 0:
            if speed >= HEADLIGHT_SPEED_THRESHOLD:
                return False, (
                    f"[Safety] Headlights cannot be turned off at {speed} km/h. "
                    "Visibility is required at this speed."
                )
            if state.get("headlights", False):
                return True, (
                    "Turning headlights OFF while currently on. "
                    "Ensure this is intentional (not in a tunnel or at night)."
                )

        # Policy 3: Temperature comfort guards
        if cmd == "SET_TEMPERATURE":
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                v = 22
            if v <= 17:
                return True, "Cabin temperature set very low. Monitor passenger comfort."
            if v >= 29:
                if speed >= TEMP_HIGH_SPEED_WARN:
                    return True, (
                        f"Cabin temperature set very high at {speed} km/h. "
                        "High cabin heat at speed may affect driver alertness."
                    )
                return True, "Cabin temperature set very high. Monitor passenger comfort."

        # Policy 4: Fan speed – warn if fan turned off while AC running
        if cmd == "SET_FAN_SPEED":
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                v = 1
            if v == 1 and state.get("ac_enabled", False):
                return True, (
                    "Fan set to minimum while AC is on. "
                    "Air circulation may be insufficient."
                )

        return True, None

    # ── Dynamic block list management ─────────────────────────────────────────

    @staticmethod
    def block_command(cmd: str) -> None:
        """Dynamically add a command to the block list (e.g. valet mode)."""
        _BLOCKED_COMMANDS.add(cmd)

    @staticmethod
    def unblock_command(cmd: str) -> None:
        """Remove a command from the dynamic block list."""
        _BLOCKED_COMMANDS.discard(cmd)


# ── Standalone utility ────────────────────────────────────────────────────────

def is_gibberish(text: str) -> bool:
    """
    Heuristic gibberish detector.
    Returns True for keyboard mashing, random strings, or very short noise.
    """
    t = text.lower().strip()

    if len(t) < 2:
        return True

    alpha = re.sub(r"[^a-z]", "", t)
    if not alpha:
        return True

    # Vowel ratio — real English has >15% vowels
    vowels = sum(1 for c in alpha if c in "aeiou")
    if len(alpha) > 4 and vowels / len(alpha) < 0.10:
        return True

    # Long consonant run (>5 consecutive)
    if re.search(r"[^aeiou]{6,}", alpha):
        return True

    # Single long token with no known roots — likely gibberish
    _KNOWN = {
        "temp", "fan", "ac", "air", "sun", "roof", "window", "light",
        "head", "bright", "dark", "dim", "hot", "cold", "warm", "cool",
        "open", "close", "on", "off", "hi", "hey", "hello", "help",
        "set", "turn", "make", "increase", "decrease", "raise", "lower",
        "dog", "mode", "bye", "good", "night", "morning", "evening",
        "thanks", "thank", "okay", "great", "yeah", "yes", "no",
        "status", "reset", "focus", "undo", "back", "actually", "wait",
        "remember", "save", "usual", "preference",
    }
    if " " not in t and len(t) > 5:
        if not any(root in t for root in _KNOWN):
            return True

    return False
