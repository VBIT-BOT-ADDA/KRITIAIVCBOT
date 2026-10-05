import os
import io
import wave
import time
import asyncio
import audioop

from groq import Groq


# ============================================================
# CONFIG
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    print("[Voice Engine] WARNING: GROQ_API_KEY is not set.")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

STT_MODEL = "whisper-large-v3-turbo"

# PyTgCalls raw audio is normally PCM 16-bit / 48 kHz.
INPUT_SAMPLE_RATE = 48000
INPUT_CHANNELS = 2
SAMPLE_WIDTH = 2

# Convert to 16 kHz mono before sending to Whisper.
STT_SAMPLE_RATE = 16000
STT_CHANNELS = 1

# Voice detection settings.
FRAME_MS = 30
FRAME_BYTES = int(
    INPUT_SAMPLE_RATE * (FRAME_MS / 1000) * INPUT_CHANNELS * SAMPLE_WIDTH
)

SILENCE_TIMEOUT = 0.85
MIN_SPEECH_SECONDS = 0.45
MAX_SPEECH_SECONDS = 12.0

ENERGY_THRESHOLD = 450

TRIGGERS = (
    "hello kriti",
    "hey kriti",
    "hi kriti",
    "kriti",
)


# ============================================================
# STATE
# ============================================================

class VoiceEngine:
    def __init__(self):
        self.buffer = bytearray()

        self.speech_started = False
        self.speech_started_at = 0.0
        self.last_voice_at = 0.0

        self.processing = False
        self.paused = False

        self.lock = asyncio.Lock()

    # ========================================================
    # AUDIO HELPERS
    # ========================================================

    @staticmethod
    def pcm_to_wav(
        pcm_data: bytes,
        sample_rate: int = STT_SAMPLE_RATE,
        channels: int = STT_CHANNELS,
    ) -> bytes:

        output = io.BytesIO()

        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

        return output.getvalue()

    @staticmethod
    def prepare_for_stt(pcm_data: bytes) -> bytes:
        """
        Convert:
            48kHz stereo PCM16
        into:
            16kHz mono PCM16
        """

        if not pcm_data:
            return b""

        try:
            mono = audioop.tomono(
                pcm_data,
                SAMPLE_WIDTH,
                0.5,
                0.5,
            )

            resampled, _ = audioop.ratecv(
                mono,
                SAMPLE_WIDTH,
                1,
                INPUT_SAMPLE_RATE,
                STT_SAMPLE_RATE,
                None,
            )

            return resampled

        except Exception as error:
            print(f"[Voice Engine] Audio conversion error: {error}")
            return b""

    @staticmethod
    def is_voice(frame: bytes) -> bool:
        if not frame:
            return False

        try:
            rms = audioop.rms(
                frame,
                SAMPLE_WIDTH,
            )

            return rms >= ENERGY_THRESHOLD

        except Exception:
            return False

    # ========================================================
    # TRIGGER DETECTION
    # ========================================================

    @staticmethod
    def contains_trigger(text: str) -> bool:
        if not text:
            return False

        cleaned = " ".join(
            text.lower()
            .replace(",", " ")
            .replace(".", " ")
            .replace("!", " ")
            .replace("?", " ")
            .replace("-", " ")
            .split()
        )

        for trigger in TRIGGERS:
            if trigger in cleaned:
                return True

        return False

    # ========================================================
    # GROQ SPEECH TO TEXT
    # ========================================================

    async def transcribe(self, pcm_data: bytes) -> str:

        if not groq_client:
            print("[Voice Engine] GROQ_API_KEY missing.")
            return ""

        prepared_audio = self.prepare_for_stt(
            pcm_data
        )

        if not prepared_audio:
            return ""

        wav_data = self.pcm_to_wav(
            prepared_audio
        )

        try:

            def do_transcription():
                file_object = io.BytesIO(
                    wav_data
                )

                file_object.name = "voice.wav"

                result = groq_client.audio.transcriptions.create(
                    file=file_object,
                    model=STT_MODEL,
                    response_format="json",
                    temperature=0.0,
                )

                return result.text.strip()

            text = await asyncio.to_thread(
                do_transcription
            )

            if text:
                print(
                    f"[Voice Engine] Transcript: {text}"
                )

            return text or ""

        except Exception as error:

            print(
                f"[Voice Engine] Groq STT error: {error}"
            )

            return ""

    # ========================================================
    # PROCESS COMPLETE SENTENCE
    # ========================================================

    async def process_audio(
        self,
        pcm_data: bytes,
        callback,
    ):

        if self.processing or self.paused:
            return

        duration = (
            len(pcm_data)
            / (
                INPUT_SAMPLE_RATE
                * INPUT_CHANNELS
                * SAMPLE_WIDTH
            )
        )

        if duration < MIN_SPEECH_SECONDS:
            return

        self.processing = True

        try:

            transcript = await self.transcribe(
                pcm_data
            )

            if not transcript:
                return

            if not self.contains_trigger(
                transcript
            ):
                print(
                    "[Voice Engine] No Kriti trigger."
                )
                return

            print(
                "[Voice Engine] Kriti trigger detected!"
            )

            await callback(
                transcript
            )

        except Exception as error:

            print(
                f"[Voice Engine] Processing error: {error}"
            )

        finally:

            self.processing = False

    # ========================================================
    # RAW AUDIO CALLBACK
    # ========================================================

    async def handle_frame(
        self,
        frame: bytes,
        callback,
    ):

        if self.paused:
            return

        if not frame:
            return

        now = time.monotonic()

        voice = self.is_voice(
            frame
        )

        if voice:

            if not self.speech_started:

                self.speech_started = True
                self.speech_started_at = now

                self.buffer.clear()

                print(
                    "[Voice Engine] Speech started."
                )

            self.last_voice_at = now

            self.buffer.extend(
                frame
            )

            elapsed = (
                now - self.speech_started_at
            )

            if elapsed >= MAX_SPEECH_SECONDS:

                audio = bytes(
                    self.buffer
                )

                self.buffer.clear()
                self.speech_started = False

                asyncio.create_task(
                    self.process_audio(
                        audio,
                        callback,
                    )
                )

            return

        # ----------------------------------------------------
        # SILENCE
        # ----------------------------------------------------

        if not self.speech_started:
            return

        self.buffer.extend(
            frame
        )

        silence_duration = (
            now - self.last_voice_at
        )

        if silence_duration >= SILENCE_TIMEOUT:

            audio = bytes(
                self.buffer
            )

            self.buffer.clear()
            self.speech_started = False

            asyncio.create_task(
                self.process_audio(
                    audio,
                    callback,
                )
            )

    # ========================================================
    # PAUSE / RESUME
    # ========================================================

    def pause(self):
        self.paused = True
        self.buffer.clear()
        self.speech_started = False

    def resume(self):
        self.buffer.clear()
        self.speech_started = False
        self.paused = False


voice_engine = VoiceEngine()
