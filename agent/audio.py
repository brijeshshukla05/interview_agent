from gtts import gTTS
import speech_recognition as sr
import io
import os

def text_to_speech_bytes(text: str) -> io.BytesIO:
    """
    Converts text to speech using gTTS and returns audio bytes.
    """
    try:
        if not text.strip():
            return None
            
        tts = gTTS(text=text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception as e:
        print(f"Error in TTS: {e}")
        return None

def audio_bytes_to_text(audio_bytes: bytes) -> str:
    """
    Converts audio bytes to text using SpeechRecognition.
    Assumes wav format if possible, but might need conversion.
    'streamlit-mic-recorder' returns wav bytes usually.
    """
    r = sr.Recognizer()
    try:
        # Create a file-like object from bytes
        audio_file = io.BytesIO(audio_bytes)
        
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error converting audio: {e}"
