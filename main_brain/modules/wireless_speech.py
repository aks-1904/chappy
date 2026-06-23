import logging
import numpy as np
import whisper
import threading
import time
import tempfile
import wave
from pathlib import Path
from typing import Optional
import pyttsx3
import scipy.io.wavfile as swf
import scipy.signal as ss
import pyaudio

from modules.speech import SpeechModule
from config.settings import AUDIO, WIRELESS

log = logging.getLogger(__name__)

SAMPLE_RATE   = 16000
BYTES_PER_S   = SAMPLE_RATE * 2   # int16
SILENCE_THRESH = AUDIO["vad_threshold"] * 32768

class WirelessSpeechModule(SpeechModule):
    def __init__(self, wireless_bridge=None):
        super().__init__()
        self._wireless = wireless_bridge
        self._acc_buf: list[np.ndarray] = [] # accumulated PCM chunks
        self._acc_bytes: int = 0
        self._silence_chunks: int = 0
        self._vad_active: bool = False
        self._no_audio_signal: bool = True
        self._last_audio_ts: float = 0.0

        # Silence detection params (mirrors USB mic logic)
        self._chunk_bytes = 1600 * 2 # ~100ms at 16kHz int 16
        self._max_silence = int(AUDIO["silence_timeout"] * SAMPLE_RATE / (self._chunk_bytes // 2))
        self._max_chunks = int(AUDIO["max_record_seconds" * SAMPLE_RATE / (self._chunk_bytes // 2)])

    def start(self):
        self._init_tts()
        if self._wireless is None:
            log.warning("[WirelessSpeech] No bridge - falling back to USB mic")
            super().start()
            return
        
        log.info(f"[WirelessSpeech] Loading Whisper '{AUDIO['whisper_model']}'...")
        self._whisper_model = whisper.load_model(AUDIO["whisper_model"])
        log.info("[WirelessSpeech] Whisper ready")

        # Start audio ingestion thread
        threading.Thread(
            target=self._wireless_audio_loop,
            name="WirelessAudioIngest",
            daemon=True,
        ).start()
        log.info("[WirelessSpeech] Wireless audio ingestion started")

    def _wireless_audio_loop(self):
        while True:
            if not self._wireless:
                time.sleep(0.05)
                continue

            chunk = self._wireless.poll_audio_pcm()
            if chunk is None:
                # No data - yield
                time.sleep(0.01)
                continue

            self._no_audio_signal = False
            self._last_audio_ts = time.time()

            # VAD: compute RMS energy
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

            if rms >= SILENCE_THRESH:
                # Voice detected
                self._vad_active = True
                self._silence_chunks = 0
                self._acc_buf.append(chunk)
                self._acc_bytes += len(chunk) * 2

            elif self._vad_active:
                # Silence after speech
                self._acc_buf.append(chunk)
                self._acc_bytes += len(chunk) * 2
                self._silence_chunks += 1

                # End of utterance conditions
                if(
                    self._silence_chunks >= self._max_silence or self._acc_bytes > self._max_chunks * self._chunk_bytes
                ):
                    self._flush_utterance()
            # else: silence before speech - can be ignored

    def _flush_utterance(self):
        if not self._acc_buf:
            return
        
        pcm_all = np.concatenate(self._acc_buf).astype(np.int16)
        self._acc_buf.clear()
        self._acc_bytes = 0
        self._vad_active = False
        self._silence_chunks = 0

        # Write to temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
            with wave.open(f, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm_all.tobytes())

        try:
            result = self._whisper_model.transcribe(
                tmp,
                language=AUDIO["whisper_language"],
                fp16=False,
            )
            text = result["text"].strip()
            if text:
                log.info(f"[WirelessSpeech] Heard: {text!r}")
                self._stt_queue.put(text)
                if self.on_transcription:
                    self.on_transcription(text)

        except Exception as e:
            log.error(f"[WirelessSpeech] Whisper error: {e}")
        finally:
            Path(tmp).unlink(missing_ok=True)

    def speak(self, text: str, emotion: str = "neutral", blocking: bool = False):
        if not text.strip():
            return
        
        def _do_speak():
            with self._tts_lock:
                self._speaking = True
                pcm_bytes = self._render_tts_to_pcm(text, emotion)
                if pcm_bytes:
                    # Send to ESP32 speaker
                    if self._wireless and self._wireless.connected:
                        self._wireless.send_tts_audio(pcm_bytes, SAMPLE_RATE)
                        log.debug(f"[WirelessSpeech] Sent {len(pcm_bytes)}B to ESP32 speaker")

                    # Also play locally if configured
                    if WIRELESS.get("dual_speaker_output", False):
                        self._play_pcm_local(pcm_bytes)
                else:
                    # Fallback: pyttsx3 local only
                    self._speak_with_emotion(text, emotion)
                self._speaking = False

        if blocking:
            _do_speak()
        else:
            threading.Thread(target=_do_speak, daemon=True).start()
    
    def _render_tts_to_pcm(self, text: str, emotion: str) -> Optional[bytes]:
        if not self._tts_engine:
            return None

        rate_mult, vol_mult = self._EMOTION_PARAMS.get(
            emotion.lower(), (1.0, 1.0)
        )
        base_rate = AUDIO["tts_rate"]
        base_vol  = AUDIO["tts_volume"]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name

        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            vi = AUDIO["tts_voice_index"]
            if voices and vi < len(voices):
                engine.setProperty("voice", voices[vi].id)
            
            engine.setProperty("rate",   int(base_rate * rate_mult))
            engine.setProperty("volume", base_vol * vol_mult)
            engine.save_to_file(text, tmp)
            engine.runAndWait()
            engine.stop()

            # Read WAV -> resample to 16kHz mono int16 if needed
            return self._wav_to_pcm16k(tmp)

        except Exception as e:
            log.error(f"[WirelessSpeech] TTS render error: {e}")
            return None
        finally:
            Path(tmp).unlink(missing_ok=True)

    @staticmethod
    def _wav_to_pcm16k(wav_path: str) -> Optional[bytes]:
        sr, data = swf.read(wav_path)
        # Mono
        if data.ndim > 1:
            data = data[:, 0]
        # Resample to 16kHz
        if sr != 16000:
            num_samples = int(len(data) * 16000 / sr)
            data = ss.resample(data, num_samples).astype(np.int16)
        return data.astype(np.int16).tobytes()
    
    def _play_pcm_local(self, pcm_bytes: bytes):
        try:
            pa = pyaudio.PyAudio()
            stm = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                output=True,
            )
            stm.write(pcm_bytes)
            stm.stop_stream()
            stm.close()
            pa.terminate()
        except Exception as e:
            log.debug(f"[WirelessSpeech] Local playback error: {e}")

    @property
    def has_audio_signal(self) -> bool:
        if self._wireless is None:
            return True # USB mic assumed present
        if self._last_audio_ts == 0:
            return False
        
        return time.time() - self._last_audio_ts < 10.0