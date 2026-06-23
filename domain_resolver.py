"""
domain_resolver.py
Production domain ontology layer.

Maps high-level semantic/metaphorical expressions to concrete CAN intents.
Sits between RegexIntentResolver and RAG/SLM in the pipeline — catches
expressions that regex patterns miss but that don't need a full LLM.

Examples
────────
  "it's boiling in here"    → SET_TEMPERATURE 17  (max-cool)
  "I'm freezing"            → SET_TEMPERATURE 26  (warm up)
  "let some fresh air in"   → SET_POSITION 50     (open sunroof halfway)
  "it's too stuffy"         → SET_POSITION 50 + fan boost
  "dim it down"             → SET_BRIGHTNESS 20
  "night mode"              → SET_BRIGHTNESS 10 + SET_HEADLIGHTS 1
"""

import time

# ── Semantic word-banks ───────────────────────────────────────────────────────

_HOT   = {"greenhouse", "boiling", "roasting", "sweltering", "melting", "sauna",
           "scorching", "burning", "baking", "steaming", "too hot", "really hot",
           "so hot", "blazing"}
_COLD  = {"freezing", "icebox", "arctic", "antarctica", "shivering", "chilly",
           "frigid", "too cold", "really cold", "so cold", "icy", "frost"}
_FRESH = {"stuffy", "claustrophobic", "fresh air", "breeze", "muggy", "stale air",
          "suffocating", "breathe", "ventilate", "airy"}
_DIM   = {"too bright", "too harsh", "glaring", "dim it", "dim the lights",
          "hurting my eyes", "blinding"}
_NIGHT = {"night mode", "night drive", "driving at night", "it's dark outside",
          "dark mode", "dark outside"}
_FOCUS = {"focus mode", "do not disturb", "concentrate", "no distractions"}


# ── Intent catalogue ──────────────────────────────────────────────────────────
# Each entry resolves to a single CAN intent dict.

_INTENTS = {
    "HOT": {
        "can_id":    "0x101",
        "command":   "SET_TEMPERATURE",
        "value":     18,
        "reason":    "Domain: cabin feels hot — cooling to 18°C.",
        "confidence": 0.82,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
    },
    "COLD": {
        "can_id":    "0x101",
        "command":   "SET_TEMPERATURE",
        "value":     25,
        "reason":    "Domain: cabin feels cold — warming to 25°C.",
        "confidence": 0.82,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
    },
    "FRESH_AIR": {
        "can_id":    "0x102",
        "command":   "SET_POSITION",
        "value":     50,
        "reason":    "Domain: stuffy/fresh-air request — sunroof 50%.",
        "confidence": 0.78,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
    },
    "DIM_LIGHTS": {
        "can_id":    "0x103",
        "command":   "SET_BRIGHTNESS",
        "value":     20,
        "reason":    "Domain: too bright — dimming dashboard to 20%.",
        "confidence": 0.80,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
    },
    "NIGHT_MODE": {
        "can_id":    "0x103",
        "command":   "SET_BRIGHTNESS",
        "value":     10,
        "reason":    "Domain: night-mode — low brightness + headlights.",
        "confidence": 0.85,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
        "_follow_up": {               # secondary action delivered to caller
            "can_id":  "0x103",
            "command": "SET_HEADLIGHTS",
            "value":   1,
            "reason":  "Night mode: headlights on.",
            "confidence": 0.85,
            "handled_by": "DomainResolver",
            "latency": "0.2ms",
        },
    },
    "FOCUS_MODE": {
        "can_id":    "0x101",
        "command":   "SET_FAN_SPEED",
        "value":     1,
        "reason":    "Domain: focus mode — minimal fan noise.",
        "confidence": 0.75,
        "handled_by": "DomainResolver",
        "latency":   "0.2ms",
    },
}


class DomainResolver:
    """
    Lightweight semantic resolver.
    resolve(text) → intent dict | None
    """

    def resolve(self, text: str) -> dict | None:
        t = text.lower()
        t0 = time.perf_counter()

        tag = None
        if any(w in t for w in _HOT):
            tag = "HOT"
        elif any(w in t for w in _COLD):
            tag = "COLD"
        elif any(w in t for w in _FRESH):
            tag = "FRESH_AIR"
        elif any(w in t for w in _NIGHT):
            tag = "NIGHT_MODE"
        elif any(w in t for w in _DIM):
            tag = "DIM_LIGHTS"
        elif any(w in t for w in _FOCUS):
            tag = "FOCUS_MODE"

        if tag is None:
            return None

        elapsed = (time.perf_counter() - t0) * 1000
        intent  = dict(_INTENTS[tag])           # shallow copy — safe to mutate
        intent["latency"] = f"{elapsed:.2f}ms"
        return intent
