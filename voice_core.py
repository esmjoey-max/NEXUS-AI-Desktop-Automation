import speech_recognition as sr
import pyttsx3
import threading
import whisper
import os
import logging
from dataclasses import dataclass
import sys

# Initialize COM library on the current thread for Windows
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass

logger = logging.getLogger("VoiceCore")

@dataclass
class VoiceConfig:
    tts_voice: str = "en-US-GuyNeural"
    tts_rate: str = "200"
    tts_pitch: str = "100"
    whisper_model: str = "base"
    noise_gate_db: float = -40.0

class VoiceSystem:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.recognizer = sr.Recognizer()
        
        # Initialize pyttsx3 safely
        try:
            self.engine = pyttsx3.init()
        except Exception as e:
            logger.critical(f"Failed to initialize pyttsx3 engine: {e}")
            self.engine = None
            
        self.source = sr.Microphone()
        self.audio_data = None
        
        # Initialize voice settings if engine is available
        if self.engine:
            self.update_voice(voice=config.tts_voice, rate=config.tts_rate)
        
        # Load Whisper with CPU fallback to avoid GPU kernel incompatibility
        logger.info("Loading Whisper transcription model...")
        try:
            self.whisper_model = whisper.load_model(config.whisper_model, device="cpu")
            logger.info("Voice system ready.")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.whisper_model = None

    def get_microphone_list(self):
        """Returns a list of available microphone indices and names."""
        try:
            return [(i, name) for i, name in enumerate(sr.Microphone.list_microphone_names())]
        except Exception:
            return []

    def set_device(self, device_index: int):
        """Sets the active microphone for capture."""
        try:
            self.source = sr.Microphone(device_index=device_index)
        except Exception as e:
            logger.error(f"Failed to set microphone device: {e}")

    def update_voice(self, voice=None, rate=None):
        if not self.engine:
            return
            
        # 1. Handle Rate
        if rate:
            clean_rate = str(rate).replace("+", "").replace("%", "")
            try: 
                self.engine.setProperty('rate', int(clean_rate))
            except ValueError: 
                self.engine.setProperty('rate', 200)
                
        # 2. Handle Voice safely with a fallback chain
        if voice:
            try:
                self.engine.setProperty('voice', voice)
            except Exception as e:
                logger.error(f"Failed to set configured voice '{voice}': {e}")
                try:
                    # Fallback: Attempt to use the first available system voice
                    available_voices = self.engine.getProperty('voices')
                    if available_voices:
                        logger.info(f"Falling back to default system voice: {available_voices[0].id}")
                        self.engine.setProperty('voice', available_voices[0].id)
                except Exception as critical_err:
                    logger.critical(f"Voice engine completely failed to assign a voice track: {critical_err}")

    def start_listening(self):
        """Starts non-blocking background audio capture."""
        def _listen():
            try:
                with self.source as s:
                    self.recognizer.adjust_for_ambient_noise(s, duration=0.5)
                    self.audio_data = self.recognizer.listen(s, timeout=10, phrase_time_limit=10)
            except Exception as e:
                logger.error(f"Listening error: {e}")
        
        threading.Thread(target=_listen, daemon=True).start()

    def stop_listening_and_transcribe(self) -> str:
        """Saves captured audio to a temp file and transcribes using Whisper."""
        if not self.audio_data or not self.whisper_model:
            return ""
            
        temp_file = "temp_voice.wav"
        try:
            with open(temp_file, "wb") as f:
                f.write(self.audio_data.get_wav_data())
            
            # Perform transcription
            result = self.whisper_model.transcribe(temp_file, fp16=False)
            return result["text"].strip()
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def speak(self, text: str, blocking: bool = False):
        """Speaks text using the TTS engine."""
        if not self.engine:
            return
            
        def _say():
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS Engine failed to speak: {e}")
        
        if blocking:
            _say()
        else:
            threading.Thread(target=_say, daemon=True).start()