"""
voice_service.py — Flask-compatible wrapper for TTS and STT.
Ports the TTS logic from chatbot/tts_service.py and the STT logic from chatbot/ai_services.py
without Streamlit dependencies.
"""

import io
import asyncio
import importlib.util
import os
import edge_tts
from openai import OpenAI
from config import Config

# Load chatbot config directly by path to avoid shadowing
_chatbot_config_path = os.path.join(os.path.dirname(__file__), "chatbot", "config.py")
_spec = importlib.util.spec_from_file_location("chatbot_config", _chatbot_config_path)
_chatbot_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_chatbot_config)

EDGE_TTS_VOICE = _chatbot_config.EDGE_TTS_VOICE
EDGE_TTS_RATE  = _chatbot_config.EDGE_TTS_RATE
GROQ_BASE_URL  = _chatbot_config.GROQ_BASE_URL
WHISPER_MODEL  = getattr(_chatbot_config, "WHISPER_MODEL", "whisper-large-v3-turbo")


def _clean_text(text: str) -> str:
    """Strip markdown formatting that sounds awkward when spoken."""
    return (
        text.replace("**", "")
            .replace("*", "")
            .replace("`", "")
            .replace("#", "")
            .replace("→", " to ")
            .replace("—", ", ")
            .replace("&amp;", "and")
            .replace("&", "and")
    )


async def _synthesize_async(text: str, voice: str) -> bytes:
    """Async Edge-TTS synthesis. Returns MP3 bytes in memory."""
    clean = _clean_text(text)
    if not clean.strip():
        return b""
    clean = clean[:3000]
    communicate = edge_tts.Communicate(clean, voice, rate=EDGE_TTS_RATE)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    buffer.seek(0)
    return buffer.read()


def synthesize_tts(text: str, voice: str = EDGE_TTS_VOICE) -> bytes:
    """
    Synchronous wrapper for Edge-TTS synthesis.
    Returns MP3 bytes.
    """
    if not text or not text.strip():
        return b""
    try:
        # Use asyncio.run directly (Flask usually runs requests in threads without existing event loops)
        return asyncio.run(_synthesize_async(text, voice))
    except Exception as e:
        print(f"[TTS Error] {e}")
        return b""


def call_stt(audio_bytes: bytes) -> str:
    """
    Transcribe audio using Groq's Whisper API.
    Args:
        audio_bytes: Raw audio bytes (WebM/WAV)
    Returns:
        Transcribed text, or empty string on failure
    """
    if not Config.GROQ_API_KEY:
        return ""
    try:
        client = OpenAI(api_key=Config.GROQ_API_KEY, base_url=GROQ_BASE_URL)
        buf = io.BytesIO(audio_bytes)
        buf.name = "recording.webm"  # Groq Whisper accepts webm
        result = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=buf,
            response_format="text",
        )
        return (result if isinstance(result, str) else result.text).strip()
    except Exception as e:
        print(f"[STT Error] {e}")
        return f"[Transcription error: {e}]"
