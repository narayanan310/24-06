import asyncio
import os
import sys

# Add the edge-auto-assistant path so we can import modules
sys.path.append("/home/pi/edge-auto-assistant")

from main import _resolve_clause, _execute_intent
from conversation_layer import ConversationLayer
from safety_supervisor import is_gibberish, SafetySupervisor
from state_manager import StateManager
from regex_mapper import RegexIntentResolver
from rag_resolver import RAGResolver
from slm_resolver import SLMIntentResolver
from macro_engine import MacroEngine
from dialogue_manager import DialogueManager
from context_window import ContextWindow
from context_resolver import ContextResolver
from preference_memory import PreferenceMemory
from virtual_can_bus import VirtualCANBus

# Instantiate
sm = StateManager()
safety = SafetySupervisor(sm)
macro_eng = MacroEngine()
regex_eng = RegexIntentResolver()
rag_eng = RAGResolver()
slm_eng = SLMIntentResolver()
dlg = DialogueManager()
ctx_win = ContextWindow()
ctx_res = ContextResolver()
prefs = PreferenceMemory()
conv_lay = ConversationLayer()
bus = VirtualCANBus()
conv_lay = ConversationLayer()

# Mock the _say function so we can trace what would be spoken
spoken_log = []
def mock_say(text):
    spoken_log.append(text)
    print(f"  [TTS Spoke] {text}")

import main
main._say = mock_say

# We need the SLM ready for the tests
slm_ready = True

# We'll build a helper to run commands exactly like main loop does
async def simulate(utterance):
    print(f"\n[{utterance.upper()}]")
    spoken_log.clear()
    raw = utterance.strip()
    
    if is_gibberish(raw):
        print("  [Result] Blocked as gibberish.")
        return
        
    macro = macro_eng.match(raw)
    if macro:
        print(f"  [Result] Macro: {macro['display']}")
        return
        
    pref_action = prefs.detect(raw)
    if pref_action:
        print(f"  [Result] Preference memory triggered.")
        return

    # Check Dialogue repairs
    if dlg.is_repair(raw):
        action, undo_intent = dlg.resolve_repair(raw)
        print(f"  [Result] Repair detected: {action}")
        if undo_intent:
            print(f"  [Result] Undo intent: {undo_intent}")
        return

    # Check Conversational Layer
    reply = conv_lay.respond(raw)
    if reply:
        print(f"  [Result] Conversation layer: {reply}")
        return

    # Intent routing
    from intent_splitter import split_intents
    clauses = split_intents(raw)
    failed = []
    for c in clauses:
        print(f"  [Routing clause] '{c}'")
        intent = _resolve_clause(c, ctx_win, ctx_res, regex_eng, rag_eng, slm_eng, slm_ready)
        if intent:
            print(f"  [Result] Resolved to: {intent['command']} {intent.get('value', '')} (via {intent.get('handled_by')})")
            # Create a supervisor instance since _execute_intent needs it
            safety = SafetySupervisor(sm)
            await _execute_intent(c, intent, bus, safety, ctx_win, dlg, sm, macro_eng)
        else:
            failed.append(c)
            
    if failed:
        if slm_ready:
            print(f"  [Result] Dropping to SLM chat for: {failed}")
            reply = slm_eng.chat(raw)
            print(f"  [Result] SLM Chat replied: {reply}")

async def run_simulation():
    # 1. Normal Regex
    await simulate("set the temperature to 21 degrees")
    
    # 2. Contextual Regex (Abnormal context switch)
    await simulate("actually make it 23")
    
    # 3. Macro logic
    await simulate("warm me up")
    
    # 4. Safety Logic (Sunroof + AC)
    sm.update("ac_enabled", True)
    await simulate("open the sunroof to 100 percent")
    
    # 5. Conversation Layer
    await simulate("help me")
    
    # 6. RAG test
    await simulate("how do i manually reset the sunroof")
    
    # 7. SLM Chat Fallback (Abnormal input)
    await simulate("my favorite color is blue")
    
    # 8. Gibberish (Abnormal input)
    await simulate("asdfjklqwerty")
    
    # 9. Cross-domain repair
    await simulate("turn on the headlights")
    await simulate("wait no i meant the screen")
    
    # 10. Acoustic Comfort
    await simulate("it's too loud in here")
    
    print("\n--- SIMULATION COMPLETE ---")

asyncio.run(run_simulation())
