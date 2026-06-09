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