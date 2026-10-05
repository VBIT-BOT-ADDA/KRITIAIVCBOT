import os
import asyncio
import io
import wave
import time
import math
import struct
import tempfile

from google import genai


# ============================================================
# GEMINI CONFIG
# ============================================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    "",
)

if not GEMINI_API_KEY:
    print(
        "[Voice Engine] WARNING: GEMINI_API_KEY is not set."
    )


gemini_client = (
    genai.Client(
        api_key=GEMINI_API_KEY
    )
    if GEMINI_API_KEY
    else None
)


GEMINI_STT_MODEL = "gemini-2.5-flash"


# ============================================================
# AUDIO FORMAT
# ============================================================

INPUT_SAMPLE_RATE = 48000

INPUT_CHANNELS = 2

SAMPLE_WIDTH = 2


# ============================================================
# SPEECH SETTINGS
# ============================================================

SILENCE_TIMEOUT = 0.85

MIN_SPEECH_SECONDS = 0.45

MAX_SPEECH_SECONDS = 12.0

ENERGY_THRESHOLD = 450


# ============================================================
# KRITI TRIGGERS
# ============================================================

TRIGGERS = (
    "hello kriti",
    "hey kriti",
    "hi kriti",
    "kriti",
)


# ============================================================
# VOICE ENGINE
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
    # PCM → WAV
    # ========================================================

    @staticmethod
    def pcm_to_wav(
        pcm_data: bytes,
    ) -> bytes:

        output = io.BytesIO()

        with wave.open(
            output,
            "wb",
        ) as wav_file:

            wav_file.setnchannels(
                INPUT_CHANNELS
            )

            wav_file.setsampwidth(
                SAMPLE_WIDTH
            )

            wav_file.setframerate(
                INPUT_SAMPLE_RATE
            )

            wav_file.writeframes(
                pcm_data
            )

        return output.getvalue()


    # ========================================================
    # RMS
    # ========================================================

    @staticmethod
    def calculate_rms(
        frame: bytes,
    ) -> float:

        if not frame:
            return 0.0

        usable_length = (
            len(frame)
            - (len(frame) % SAMPLE_WIDTH)
        )

        if usable_length <= 0:
            return 0.0

        try:

            samples = struct.unpack(
                "<{}h".format(
                    usable_length // SAMPLE_WIDTH
                ),
                frame[:usable_length],
            )

            if not samples:
                return 0.0

            square_sum = sum(
                sample * sample
                for sample in samples
            )

            return math.sqrt(
                square_sum / len(samples)
            )

        except Exception:

            return 0.0


    # ========================================================
    # VOICE DETECTION
    # ========================================================

    @classmethod
    def is_voice(
        cls,
        frame: bytes,
    ) -> bool:

        if not frame:
            return False

        rms = cls.calculate_rms(
            frame
        )

        return (
            rms >= ENERGY_THRESHOLD
        )


    # ========================================================
    # CLEAN TEXT
    # ========================================================

    @staticmethod
    def clean_text(
        text: str,
    ) -> str:

        if not text:
            return ""

        cleaned = text.lower()

        for character in (
            ",",
            ".",
            "!",
            "?",
            "-",
            "_",
            ":",
            ";",
        ):

            cleaned = cleaned.replace(
                character,
                " ",
            )

        return " ".join(
            cleaned.split()
        )


    # ========================================================
    # CHECK TRIGGER
    # ========================================================

    @classmethod
    def contains_trigger(
        cls,
        text: str,
    ) -> bool:

        cleaned = cls.clean_text(
            text
        )

        if not cleaned:
            return False

        for trigger in TRIGGERS:

            if trigger in cleaned:
                return True

        return False


    # ========================================================
    # GEMINI AUDIO TRANSCRIPTION
    # ========================================================

    async def transcribe(
        self,
        pcm_data: bytes,
    ) -> str:

        if not gemini_client:

            print(
                "[Voice Engine] GEMINI_API_KEY missing."
            )

            return ""

        if not pcm_data:

            return ""

        wav_data = self.pcm_to_wav(
            pcm_data
        )

        temp_path = None

        try:

            # ------------------------------------------------
            # Temporary WAV
            # ------------------------------------------------

            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            ) as temp_file:

                temp_file.write(
                    wav_data
                )

                temp_path = (
                    temp_file.name
                )


            # ------------------------------------------------
            # Gemini upload + transcription
            # ------------------------------------------------

            def do_transcription():

                uploaded_file = (
                    gemini_client.files.upload(
                        file=temp_path
                    )
                )

                prompt = """
Transcribe the speech in this audio.

Return ONLY the words spoken by the person.

Do not summarize.
Do not explain.
Do not add commentary.

Keep the original spoken language.

The speaker may use:

Hindi
English
Hinglish
Bengali
Tamil
Telugu
Marathi
Gujarati

If the person says Kriti, Hello Kriti,
Hey Kriti, or Hi Kriti, preserve those words.
"""

                response = (
                    gemini_client.models.generate_content(
                        model=GEMINI_STT_MODEL,
                        contents=[
                            prompt,
                            uploaded_file,
                        ],
                    )
                )

                if (
                    response
                    and response.text
                ):

                    return response.text.strip()

                return ""


            transcript = await asyncio.to_thread(
                do_transcription
            )

            if transcript:

                print(
                    f"[Gemini STT] {transcript}"
                )

            return transcript or ""


        except Exception as error:

            print(
                f"[Gemini STT Error] {error}"
            )

            return ""


        finally:

            if temp_path:

                try:

                    if os.path.exists(
                        temp_path
                    ):

                        os.remove(
                            temp_path
                        )

                except Exception:

                    pass


    # ========================================================
    # PROCESS COMPLETE SPEECH
    # ========================================================

    async def process_audio(
        self,
        pcm_data: bytes,
        callback,
    ):

        if self.processing:
            return

        if self.paused:
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

            print(
                "[Voice Engine] Speech too short."
            )

            return

        self.processing = True

        try:

            transcript = await self.transcribe(
                pcm_data
            )

            if not transcript:
                return

            print(
                f"[Voice Engine] Heard: {transcript}"
            )

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
    # HANDLE AUDIO FRAME
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


        # ----------------------------------------------------
        # Voice detected
        # ----------------------------------------------------

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
                now
                - self.speech_started_at
            )


            # ------------------------------------------------
            # Maximum speech duration
            # ------------------------------------------------

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
        # Silence before speech
        # ----------------------------------------------------

        if not self.speech_started:

            return


        # Keep trailing silence
        self.buffer.extend(
            frame
        )


        silence_duration = (
            now
            - self.last_voice_at
        )


        # ----------------------------------------------------
        # Speech ended
        # ----------------------------------------------------

        if (
            silence_duration
            >= SILENCE_TIMEOUT
        ):

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
    # PAUSE
    # ========================================================

    def pause(self):

        self.paused = True

        self.buffer.clear()

        self.speech_started = False


    # ========================================================
    # RESUME
    # ========================================================

    def resume(self):

        self.buffer.clear()

        self.speech_started = False

        self.paused = False


# ============================================================
# GLOBAL VOICE ENGINE
# ============================================================

voice_engine = VoiceEngine()
