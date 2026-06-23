"""
macro_engine.py
Hardcoded multi-action sequences — highest-priority resolver.

Macros bypass the entire intent pipeline. They fire atomically
with a small inter-frame gap so ECU logs remain readable.

Macros defined
──────────────
dog mode      — cracked window, 22°C, AC on, fan 2
bye           — headlights off, AC off, fan 1, sunroof closed, brightness 10
good night    — brightness 5, sunroof closed, headlights off
focus mode    — 20°C, fan 1, brightness 30 (minimal distraction)
reset         — all systems to factory defaults
"""

import asyncio


_MACROS: dict[str, dict] = {

    "dog mode": {
        "display": "Dog Mode",
        "speech": (
            "Dog mode activated. "
            "Cracking the window to 10%, "
            "climate set to 22 degrees, AC and fan on."
        ),
        "actions": [
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 10},
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 22},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
        ],
    },

    "bye": {
        "display": "Shutdown Sequence",
        "speech": (
            "Goodbye. Shutting everything down — "
            "headlights off, AC off, sunroof closed, dashboard dimmed."
        ),
        "actions": [
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 0},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 1},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 10},
        ],
    },

    "good night": {
        "display": "Good Night Sequence",
        "speech": (
            "Good night. "
            "Dimming the dashboard, closing the sunroof, lights off."
        ),
        "actions": [
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 5},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
        ],
    },

    "focus mode": {
        "display": "Focus Mode",
        "speech": (
            "Focus mode on. "
            "Optimal temperature, low fan, dimmed dashboard — "
            "reducing distractions."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 20},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 1},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 30},
        ],
    },

    "dog mode off": {
        "display": "Dog Mode Off",
        "speech": (
            "Dog mode deactivated. "
            "Closing sunroof, AC off, fan set to low."
        ),
        "actions": [
            {"can_id": "0x102", "command": "SET_POSITION",  "value": 0},
            {"can_id": "0x101", "command": "TOGGLE_AC",     "value": 0},
            {"can_id": "0x101", "command": "SET_FAN_SPEED", "value": 1},
        ],
    },

    "morning mode": {
        "display": "Morning Mode",
        "speech": (
            "Good morning! "
            "Setting a fresh 21 degrees, fan on 2, headlights off — "
            "enjoy the drive."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 21},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 70},
        ],
    },

    "night mode": {
        "display": "Night Mode",
        "speech": (
            "Night mode on. "
            "Headlights on, brightness dimmed to 20 percent for comfortable night driving."
        ),
        "actions": [
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 1},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 20},
        ],
    },

    "reset": {
        "display": "Reset to Defaults",
        "speech": (
            "Resetting all systems to defaults: "
            "22 degrees, fan 2, AC on, sunroof closed, "
            "lights off, brightness 50%."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 22},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 50},
        ],
    },

    "defrost": {
        "display": "Defrost Mode",
        "speech": (
            "Defrosting the windshield. "
            "Setting AC on to dehumidify, and fan to maximum."
        ),
        "actions": [
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 5},
        ],
    },

    "warm me up": {
        "display": "Warm Me Up",
        "speech": (
            "Warming you up. "
            "Setting temperature to 28 degrees, with a low fan to prevent cold air blasts while the heater warms up."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 28},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 0},
        ],
    },

    "cool me down": {
        "display": "Cool Me Down",
        "speech": (
            "Cooling you down. "
            "Setting temperature to 18 degrees, AC on, and fan to maximum."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 18},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 5},
        ],
    },
}

_MACROS["good morning"] = _MACROS["morning mode"]
_MACROS["morning"] = _MACROS["morning mode"]
_MACROS["good evening"] = _MACROS["night mode"]
_MACROS["evening"] = _MACROS["night mode"]
_MACROS["night"] = _MACROS["good night"]

import re

class MacroEngine:
    def match(self, text: str) -> dict | None:
        t = text.lower().strip()
        for trigger, macro in _MACROS.items():
            # Use word boundaries so 'reset' doesn't trigger on 'how do i manually reset'
            # For exact macros we only want them to trigger if the exact phrase is isolated or the main intent
            if re.search(r'\b' + re.escape(trigger) + r'\b', t):
                # Exception: 'reset' is too dangerous to trigger on just the word anywhere.
                # Only trigger 'reset' if it's explicitly 'reset systems', 'factory reset', or just the word 'reset' alone.
                if trigger == "reset":
                    if t not in ("reset", "reset systems", "factory reset", "reset to defaults"):
                        continue
                return macro
        return None

    async def execute(self, bus, macro: dict) -> None:
        for action in macro["actions"]:
            await bus.publish(action["can_id"], action["command"], action["value"])
            await asyncio.sleep(0.12)
