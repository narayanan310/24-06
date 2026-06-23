"""
audio_io.py — v4 (Faster-Whisper with Cancellation)

Why Faster-Whisper:
  - Massive vocabulary, no more [unk] tokens.
  - Better understanding of natural accents and phrasing.
  - Slower than Vosk, but much more accurate for general conversation.

Architecture:
  Microphone → sounddevice blocks (VAD) → Faster-Whisper batch → (text, confidence)
  TTS       → eSpeak subprocess (cancellable) → ALSA speaker
"""

import os
import queue
import subprocess
import threading
import numpy as np

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False
    print("[Audio] sounddevice not available — text-only mode.")

try:
    from faster_whisper import WhisperModel
    import logging
    # Suppress verbose CTranslate2 logs
    logging.getLogger("faster_whisper").setLevel(logging.CRITICAL)
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    print("[Audio] faster-whisper not installed.")

# ── Configuration ─────────────────────────────────────────────────────────────
MODEL_SIZE      = "base.en"
COMPUTE_TYPE    = "int8"
SAMPLE_RATE     = 16000
BLOCK_SIZE      = 4000      # 250ms per block
VAD_THRESHOLD   = 0.1   # Increased amplitude threshold to ignore background noise
SILENCE_LIMIT   = 5         # Blocks of silence (1.25s) before committing
SPEECH_TIMEOUT  = 30        # Max blocks (7.5s) before forced commit

# Automotive prompt bias to help Whisper without locking its vocab
INITIAL_PROMPT = "car, vehicle, sunroof, headlights, temperature, fan speed, dashboard, brightness, ac, air conditioning, open, close, increase, decrease, mode"


def _find_usb_mic() -> int | None:
    if not _SD_AVAILABLE: return None
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            name = d.get("name", "").lower()
            if d.get("max_input_channels", 0) > 0 and (
                "usb" in name or "jabra" in name or "webcam" in name or "headset" in name
            ):
                print(f"[Audio] USB mic auto-detected: [{i}] {d['name']}")
                return i
    except Exception:
        pass
    return None


class AudioIO:
    def __init__(self) -> None:
        self._speaking      = threading.Event()
        self._done_speaking = threading.Event()
        self._done_speaking.set()
        self._tts_proc      = None  # Track TTS process for cancellation
        
        self._mic_device    = _find_usb_mic()
        self._model         = None

        if not _SD_AVAILABLE or not _WHISPER_AVAILABLE:
            print("[Audio] Running in text-only mode.")
            return

        print(f"[Audio] Loading Faster-Whisper ({MODEL_SIZE}) on CPU ({COMPUTE_TYPE})...")
        self._model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
        print("[Audio] Faster-Whisper STT online.")

    def listen(self) -> tuple[str, float]:
        """
        Record audio using simple amplitude VAD, then transcribe with Whisper.
        Returns (text, confidence).
        """
        if not self._model or not _SD_AVAILABLE:
            return "", 0.0

        audio_q: queue.Queue = queue.Queue()

        def _callback(indata, frames, time_info, status):
            audio_q.put(indata.copy())

        print("[STT] Listening...", end="", flush=True)

        frames_collected = []
        speech_started = False
        silence_count = 0
        block_count = 0

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=1,
                dtype="float32",
                device=self._mic_device,
                callback=_callback
            ):
                while True:
                    data = audio_q.get()
                    amplitude = np.max(np.abs(data))

                    if not speech_started:
                        if amplitude > VAD_THRESHOLD:
                            speech_started = True
                            frames_collected.append(data)
                    else:
                        frames_collected.append(data)
                        block_count += 1
                        
                        if amplitude < VAD_THRESHOLD:
                            silence_count += 1
                        else:
                            silence_count = 0

                        # Stop conditions
                        if silence_count > SILENCE_LIMIT:
                            break
                        if block_count > SPEECH_TIMEOUT:
                            break

        except Exception as e:
            print(f"\n[STT Error] {e}")
            return "", 0.0

        if not frames_collected:
            print(" (silence)")
            return "", 0.0

        # Flatten frames to 1D array
        audio_data = np.concatenate(frames_collected).flatten()
        print(" (processing...) ", end="", flush=True)

        # Transcribe
        try:
            segments_gen, info = self._model.transcribe(
                audio_data, 
                beam_size=1, 
                language="en", 
                initial_prompt=INITIAL_PROMPT
            )
            segments = list(segments_gen)
            text = " ".join([s.text for s in segments]).strip().lower()
            
            # Confidence approximation from segments avg_logprob
            import math
            if segments:
                avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
                prob = math.exp(avg_logprob)
            else:
                prob = 0.0
            
            if text:
                print(f"-> [{text}] (confidence={prob:.0%})")
                return text, prob
            else:
                print(" (silence)")
                return "", 0.0
                
        except Exception as e:
            print(f"\n[STT Transcribe Error] {e}")
            return "", 0.0

    # ── TTS ───────────────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """Speak text via eSpeak asynchronously."""
        if not text:
            return
        self.stop_speaking() # stop any existing speech
        
        self._speaking.set()
        self._done_speaking.clear()

        def _run():
            try:
                self._tts_proc = subprocess.Popen(
                    ["espeak", "-s", "150", "-a", "180", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._tts_proc.wait()
            except FileNotFoundError:
                self._tts_proc = subprocess.Popen(
                    ["espeak-ng", "-s", "150", "-a", "180", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._tts_proc.wait()
            finally:
                self._speaking.clear()
                self._done_speaking.set()
                self._tts_proc = None

        threading.Thread(target=_run, daemon=True).start()

    def stop_speaking(self) -> None:
        """Interrupt and kill current TTS output immediately."""
        if self._tts_proc:
            try:
                self._tts_proc.kill()
            except Exception:
                pass
        self._speaking.clear()
        self._done_speaking.set()

    def wait_until_done_speaking(self, timeout: float = 15.0) -> None:
        self._done_speaking.wait(timeout=timeout)

    def is_speaking(self) -> bool:
        return self._speaking.is_set()
