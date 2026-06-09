import logging
import whisper
import pyaudio
import pyttsx3

from config.settings import AUDIO

log = logging.getLogger(__name__)

class SpeechModule:
    def __init__(self):
        self._whisper_model = None
        self._listening = False
        self._audio = pyaudio.PyAudio()
        self._tts_engine = None

    def start(self):
        self._init_tts()
        log.info(f"[Speech] Loading whisper '{AUDIO['whisper_model']}")
        self._whisper_model = whisper.load_model(AUDIO["whisper_model"])
        
        log.info("[Speech] Whisper ready")

    def stop(self):
        self._listening = False
        self._audio.terminate()
        log.info("[Speech] Stopped")

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