import logging
import whisper
import pyaudio
import pyttsx3
import threading
from typing import Optional, Callable
import numpy as np
import tempfile
import wave
from pathlib import Path
import queue
from TTS.api import TTS as CoquiTTS
import sounddevice as sd
import soundfile  as sf

from config.settings import AUDIO

# Mic Capture Settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
CHANNELS = 1
FORMAT = pyaudio.paInt16
SAMPLE_WIDTH = 2

log = logging.getLogger(__name__)

class SpeechModule:
    def __init__(self):
        self._whisper_model = None
        self._listening = False
        self._audio = pyaudio.PyAudio()
        self._tts_engine = None
        self.on_transcription: Optional[Callable[[str], None]] = None
        self._stt_queue: queue.Queue  = queue.Queue()
        self._tts_lock = threading.Lock()
        self._speaking = False

    def start(self):
        self._init_tts()
        log.info(f"[Speech] Loading whisper '{AUDIO['whisper_model']}")
        self._whisper_model = whisper.load_model(AUDIO["whisper_model"])
        
        log.info("[Speech] Whisper ready")

    def stop(self):
        self._listening = False
        self._audio.terminate()
        log.info("[Speech] Stopped")

    # Map emotion -> (rate_multiplier, volume_multiplier)
    _EMOTION_PARAMS = {
        "happy":     (1.20, 1.0),
        "sad":       (0.80, 0.8),
        "angry":     (1.10, 1.0),
        "fear":      (1.15, 0.9),
        "surprise":  (1.10, 1.0),
        "neutral":   (1.00, 1.0),
        "disgust":   (0.95, 0.85),
    }

    def get_transcription(self) -> Optional[str]:
        try:
            return self._stt_queue.get_nowait()
        except queue.Empty:
            return None

    def speak(self, text: str, emotion: str = "neutral", blocking: bool = False):
        if not text.strip():
            return
        
        def _do_speak():
            with self._tts_lock:
                self._speaking = True
                self._speak_with_emotion(text, emotion)
                self._speaking = False

        if blocking:
            _do_speak()
        else:
            t = threading.Thread(target=_do_speak, daemon=True)
            t.start()

    def _speak_with_emotion(self, text: str, emotion: str):
        rate_mult, vol_mult = self._EMOTION_PARAMS.get(emotion.lower(), (1.0, 1.0))
        base_rate = AUDIO["tts_rate"]
        base_vol = AUDIO["tts_volume"]

        if self._tts_engine:
            try:
                self._tts_engine.setProperty("rate", int(base_rate * rate_mult))
                self._tts_engine.setProperty("volume", base_vol * vol_mult)
                self._tts_engine.say(text)
                self._tts_engine.runAndWait()

                # Reset to neutral
                self._tts_engine.setProperty("rate",   base_rate)
                self._tts_engine.setProperty("volume", base_vol)
            except Exception as e:
                log.error(f"[Speech] TTS error: {e}")
        else:
            log.warning(f"[Speech] No TTS engine — would say: {text!r}")

    def _init_tts(self):
        try:
            self._tts_enine = pyttsx3.init()
            voices = self._tts_engine.getProperty("voices")
            vi = AUDIO["tts_voice_index"]
            
            if voices in vi < len(voices):
                self._tts_engine.setProperty("voice", voices[vi].id)
            self._tts_engine.setProperty("rate", AUDIO["tts_rate"])
            self._tts_engine.setProperty("volume", AUDIO["tts_volume"])

            log.info("[Speech] pyttsx3 TTS ready")
        except Exception as e:
            log.error(f"[Speech] pyttsx3 init failed: {e}")
            self._tts_engine = None

    def _record_audio(self) -> bytes:
        stream = self._audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=AUDIO.get("mic_device_index"),
            frames_per_buffer=CHUNK_SIZE,
        )
        frames = []
        silence_chunks = 0
        max_silence = int(AUDIO["silence_timeout"] * SAMPLE_RATE / CHUNK_SIZE)
        max_chunks = int(AUDIO["max_record_seconds"] * SAMPLE_RATE / CHUNK_SIZE)
        threshold = AUDIO["vad_threshold"] * 32768 # normalize to int16 range

        log.debug("[Speech Recording...]")
        for _ in range(max_chunks):
            chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            frames.append(chunk)
            amplitude = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(amplitude.astype(np.float32) ** 2))

            if rms < threshold:
                silence_chunks += 1
                if silence_chunks >= max_silence:
                    break
            else:
                silence_chunks = 0

            stream.stop_stream()
            stream.close()

            return b"".join(frames)

    def listen_once(self) -> Optional[str]:
        raw_pcm = self._record_audio()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            with wave.open(f, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(SAMPLE_WIDTH)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(raw_pcm)
        
        try:
            result = self._whisper_model.transcribe(
                tmp_path,
                language=AUDIO["whisper_language"],
                fp16=False,
            )
            text = result["text"].strip()
            log.info(f"[Speech] Heard: {text!r}")

            if self.on_transcription:
                self.on_transcription(text)
            return text
        
        except Exception as e:
            log.error(f"[Speech] Whisper error: {e}")
            return None
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def listen_loop(self):
        self._listening = True
        while self._listening:
            text = self.listen_once()
            if text:
                self._stt_queue.put(text)
    
    def start_listening_thread(self):
        t = threading.Thread(
            target=self.listen_loop,
            name="ListenThread",
            daemon=True
        )
        t.start()

        return t
    
    def speak_coqui(self, text: str, blocking: bool = False):
        """
        Use Coqui TTS instead of pyttsx3.
        Requires: pip install TTS
        Enable by setting AUDIO['tts_engine'] = 'coqui' in settings.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name

        def _do_coqui():
            self._speaking = True
            try:
                tts = CoquiTTS(model_name=AUDIO["coqui_model"], progress_bar=False)
                tts.tts_to_file(text=text, file_path=out_path)
                data, sr = sf.read(out_path)
                sd.play(data, sr)
                sd.wait()
            except Exception as e:
                log.error(f"[Speech] Coqui TTS error: {e}")
            finally:
                self._speaking = False
                Path(out_path).unlink(missing_ok=True)

        if blocking:
            _do_coqui()
        else:
            threading.Thread(target=_do_coqui, daemon=True).start()