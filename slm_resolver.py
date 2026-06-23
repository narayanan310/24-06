"""
slm_resolver.py
Llama-3.2-1B-Instruct adapter — v2 (anti-hallucination edition).

Key fixes in v2:
1. UNKNOWN escape hatch  — SLM can say "I don't know" instead of hallucinating
2. CAN ID hardcoded      — SLM only outputs function+value; Python assigns CAN ID
3. chat() method         — natural conversation for generic/non-vehicle input
4. State injection       — current vehicle state is passed into EVERY prompt
5. Memory injection      — saved user preferences injected into EVERY prompt
6. Anti-hallucination    — explicit "NEVER invent vehicle state" instruction
7. Proper Llama-3 format — uses <|begin_of_text|>... chat template
"""

import urllib.request
import json
import time
import re

# -- Hardcoded CAN ID map (NEVER trust SLM for this) --------------------------
_CMD_CAN_MAP: dict[str, str] = {
    "SET_TEMPERATURE": "0x101",
    "SET_FAN_SPEED":   "0x101",
    "TOGGLE_AC":       "0x101",
    "SET_POSITION":    "0x102",   # sunroof only
    "SET_HEADLIGHTS":  "0x103",
    "SET_BRIGHTNESS":  "0x103",
}

_VALID_CMDS = set(_CMD_CAN_MAP.keys())

# -- Value bounds (hard-clamp SLM output) -------------------------------------
_VALUE_BOUNDS: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1, 5),
    "TOGGLE_AC":       (0, 1),
    "SET_POSITION":    (0, 100),
    "SET_HEADLIGHTS":  (0, 1),
    "SET_BRIGHTNESS":  (0, 100),
}


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text, ignoring surrounding noise."""
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def _clamp(cmd: str, value: int) -> int:
    lo, hi = _VALUE_BOUNDS.get(cmd, (0, 100))
    return max(lo, min(hi, value))


def _format_state(state: dict | None) -> str:
    """Format vehicle state as a compact, readable block for prompt injection."""
    if not state:
        return ""
    ac_str = "ON" if state.get("ac_enabled") else "OFF"
    hl_str = "ON" if state.get("headlights") else "OFF"
    return (
        f"\n[Current Vehicle State — READ ONLY, DO NOT INVENT OR MODIFY]\n"
        f"Temperature: {state.get('ac_temperature', 22)}°C | "
        f"Fan Speed: {state.get('fan_speed', 2)} | "
        f"AC: {ac_str} | "
        f"Sunroof: {state.get('sunroof_position', 0)}% | "
        f"Headlights: {hl_str} | "
        f"Brightness: {state.get('brightness', 50)}%\n"
    )


def _format_memory(memory: dict | None) -> str:
    """Format saved user preferences for prompt injection."""
    if not memory:
        return ""
    lines = []
    label_map = {
        "ac_temperature": "Preferred temperature",
        "fan_speed":      "Preferred fan speed",
        "brightness":     "Preferred brightness",
    }
    for key, label in label_map.items():
        if key in memory and "value" in memory[key]:
            lines.append(f"{label}: {memory[key]['value']}")
    if not lines:
        return ""
    return "\n[User Memory — Use these as defaults for comfort queries]\n" + "\n".join(lines) + "\n"


class SLMIntentResolver:
    def __init__(self, host: str = "http://127.0.0.1:8080") -> None:
        self._url = f"{host}/completion"
        self._state:  dict | None = None   # injected by main.py before each call
        self._memory: dict | None = None   # injected by main.py before each call

    def set_state_context(self, state: dict) -> None:
        """Call this before resolve()/chat() to inject current vehicle state."""
        self._state = state

    def set_memory_context(self, memory: dict) -> None:
        """Call this before resolve()/chat() to inject saved user preferences."""
        self._memory = memory

    def resolve(self, text: str) -> dict | None:
        """
        Returns a vehicle intent dict, or None if not a vehicle command.
        None = SLM said UNKNOWN, or server is down.
        """
        start = time.monotonic()

        state_block  = _format_state(self._state)
        memory_block = _format_memory(self._memory)

        system_msg = (
            "You are a vehicle command classifier. Output ONLY valid JSON.\n"
            "Valid functions and value ranges:\n"
            "  SET_TEMPERATURE  value: 17 to 29   (cabin temperature in Celsius)\n"
            "  SET_FAN_SPEED     value: 1 to 5    (blower/fan speed)\n"
            "  TOGGLE_AC         value: 0=off, 1=on\n"
            "  SET_POSITION      value: 0=closed to 100=fully open  (sunroof)\n"
            "  SET_HEADLIGHTS    value: 0=off, 1=on\n"
            "  SET_BRIGHTNESS    value: 0 to 100  (dashboard screen)\n"
            "  UNKNOWN           (greetings, questions, chat, jokes, not a vehicle command)\n"
            "\n"
            "CRITICAL RULES:\n"
            "- NEVER mention or describe the vehicle state in your output.\n"
            "- NEVER say 'The AC is on' or describe what is currently happening.\n"
            "- NEVER invent actions that weren't requested.\n"
            "- Greetings/questions/emotions/facts/jokes → UNKNOWN\n"
            "- Stars/sky/scenic view → SET_POSITION 100 (open sunroof)\n"
            "- Hot/warm/sweating → SET_TEMPERATURE 18\n"
            "- Cold/freezing/chilly → SET_TEMPERATURE 26\n"
            "- Night/dark road → SET_HEADLIGHTS 1\n"
            "- Stuffy/no air → SET_FAN_SPEED 4\n"
            "- 'comfortable' or 'my usual' → use User Memory values if available\n"
            f"{state_block}"
            f"{memory_block}"
            "\n"
            'Output format: {"function":"NAME","value":NUMBER,"reason":"short reason"}'
        )

        prompt = (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
            f"{system_msg}\n<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n"
            f"{text}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n"
            "{"
        )

        payload = {
            "prompt":      prompt,
            "n_predict":   64,
            "temperature": 0.0,
            "stop":        ["<|eot_id|>", "<|end_of_text|>", "\n\n", "```", "User:"],
        }

        try:
            req = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                raw = result.get("content", "").strip()

                if not raw.startswith("{"):
                    raw = "{" + raw

                print(f"  [SLM Raw] {raw}")

                parsed = _extract_json(raw)
                if not parsed:
                    return None

                cmd = str(parsed.get("function", "")).strip().upper()

                if cmd in ("UNKNOWN", "NONE", "", "IGNORE", "CHAT"):
                    print("  [SLM] UNKNOWN -- not a vehicle command.")
                    return None

                if cmd not in _VALID_CMDS:
                    print(f"  [SLM] Invented command '{cmd}' -- rejected.")
                    return None

                try:
                    value = int(float(str(parsed.get("value", 0))))
                except (ValueError, TypeError):
                    print("  [SLM] Bad value -- rejected.")
                    return None

                value  = _clamp(cmd, value)
                can_id = _CMD_CAN_MAP[cmd]  # HARDCODED -- never use SLM's can_id

                return {
                    "can_id":     can_id,
                    "command":    cmd,
                    "value":      value,
                    "handled_by": "Llama-3.2-1B",
                    "reason":     str(parsed.get("reason", "Inferred by SLM")),
                    "latency":    f"{time.monotonic() - start:.2f}s",
                    "confidence": 0.61,  # SLM always gets lower confidence tag
                }

        except Exception as e:
            print(f"  [SLM Error] {e}")
            return None

    def chat(self, text: str) -> str | None:
        """
        Natural conversational reply for non-vehicle input.
        State-aware — model is told the current state but FORBIDDEN from inventing it.
        """
        start = time.monotonic()

        state_block  = _format_state(self._state)
        memory_block = _format_memory(self._memory)

        system_msg = (
            "You are ARIA, a warm and friendly AI assistant built into a car cockpit. "
            "You control climate, sunroof, headlights, and display brightness. "
            "When a driver chats with you, reply in 1-2 short friendly sentences. "
            "If they ask about something outside your control (music, maps, weather), "
            "politely say you can't help with that but offer what you can do.\n"
            "\n"
            "CRITICAL: NEVER invent or describe vehicle state. "
            "NEVER say things like 'The AC is currently on' unless told so below. "
            "NEVER say you performed an action — you only respond conversationally.\n"
            f"{state_block}"
            f"{memory_block}"
        )

        prompt = (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
            f"{system_msg}\n<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n"
            f"{text}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n"
        )

        payload = {
            "prompt":      prompt,
            "n_predict":   80,
            "temperature": 0.7,
            "top_p":       0.9,
            "stop":        ["<|eot_id|>", "<|end_of_text|>", "\n\n", "User:"],
        }

        try:
            req = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                reply = result.get("content", "").strip()
                reply = re.sub(r'<\|[^|]+\|>', '', reply).strip()
                if reply:
                    print(f"  [SLM Chat] ({time.monotonic() - start:.2f}s)")
                    return reply
                return None
        except Exception as e:
            print(f"  [SLM Chat Error] {e}")
            return None
