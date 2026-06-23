from regex_mapper import RegexIntentResolver
from macro_engine import MacroEngine
from fuzzy_normalizer import normalize
from safety_supervisor import is_gibberish
from conversation_layer import ConversationLayer
from dialogue_manager import DialogueManager

import sys
sys.path.insert(0, '/home/pi/edge-auto-assistant')

regex = RegexIntentResolver()
macro = MacroEngine()
conv  = ConversationLayer()
dlg   = DialogueManager()

tests = [
    # Comfort / emotional
    'i am feeling hot',
    'i am feeling cold',
    'it is too warm in here',
    'it is freezing',
    'i feel sleepy',
    'i cannot breathe',
    'my eyes hurt from the screen',
    'it is like a sauna in here',
    'i am sweating',
    'the car is stuffy',
    # Numeric
    'set temperature to 24',
    'fan speed 3',
    'set brightness to 40 percent',
    'open sunroof to 60 percent',
    'temperature 21 degrees',
    # Directional
    'turn up the temperature',
    'lower the fan',
    'dim the dashboard',
    'brighten the screen',
    'make it warmer',
    'a bit cooler please',
    # AC
    'turn on the ac',
    'switch off air conditioning',
    'i need the ac',
    'kill the ac',
    # Sunroof
    'open the sunroof',
    'close the sunroof',
    'sunroof half open',
    'let some fresh air in',
    'it is raining',
    'open sunroof fully',
    # Lights
    'turn on the headlights',
    'lights off',
    'it is getting dark',
    'i cannot see the road',
    # Macros
    'good morning',
    'good night',
    'dog mode',
    'focus mode',
    'cool me down',
    'warm me up',
    # Gibberish / edge
    'asdfjklqwerty',
    'xkcd',
    'open',
    '',
    # Greetings
    'hi',
    'hello',
    'thanks',
    'help',
    # Repairs
    'undo that',
    'never mind',
    # Multi-clause
    'turn on headlights and open sunroof',
    'set temp 22 and fan speed 2',
    # Spoken number forms
    'set temperature to twenty three',
    'fan speed to five',
    # Weather-driven
    'stars outside tonight',
    'too loud in here',
    # Indian English / colloquial
    'yaar its so hot in here',
    'bro the ac is killing me',
    'please close that thing on the roof',
    'can you make it a little dark in here',
    'the sun is too bright outside',
]

PASS = "\033[92m[PASS]\033[0m"
WARN = "\033[93m[WARN]\033[0m"

def classify(txt):
    if not txt.strip():
        return 'EMPTY', 'ok'
    if is_gibberish(txt):
        return 'GIBBERISH', 'ok'
    m = macro.match(txt)
    if m:
        return 'MACRO:' + m['display'], 'ok'
    r = conv.respond(txt)
    if r:
        return 'CONV:' + str(r)[:45], 'ok'
    if dlg.is_repair(txt):
        return 'REPAIR', 'ok'
    norm, _ = normalize(txt)
    i = regex.resolve(norm)
    if i:
        cmd = i['command']
        val = str(i.get('value','?'))
        rsn = i['reason'][:35]
        return 'REGEX:' + cmd + '=' + val + ' / ' + rsn, 'ok'
    return 'SLM/FAILED', 'warn'

print("=" * 90)
print(f"{'RESULT':<60} | INPUT")
print("=" * 90)
warn_count = 0
for t in tests:
    res, status = classify(t)
    tag = PASS if status == 'ok' else WARN
    print(f"{tag} {res[:57]:<57} | {t}")
    if status == 'warn':
        warn_count += 1
print("=" * 90)
print(f"Total: {len(tests)} | SLM/FAILED: {warn_count}")
