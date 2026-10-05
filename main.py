import os
import asyncio
import threading
import time

import av
import edge_tts

from google import genai

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from pytgcalls import GroupCallFactory

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    GEMINI_API_KEY,
)

from voice_engine import voice_engine


# ============================================================
# GEMINI AI
# ============================================================

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)

GEMINI_MODEL = "gemini-2.5-flash"


# ============================================================
# TELEGRAM CLIENTS
# ============================================================

user_client = Client(
    "VC_Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)

bot_client = Client(
    "VC_Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# ============================================================
# MAIN ASYNCIO LOOP
# ============================================================

MAIN_LOOP = None


# ============================================================
# RAW VOICE CHAT AUDIO
# Compatible with pytgcalls==3.0.0.dev24
# ============================================================

playback_buffer = bytearray()

playback_lock = threading.Lock()

current_vc_chat_id = None

is_kriti_speaking = False


# ============================================================
# OUTGOING AUDIO CALLBACK
# ============================================================

def on_played_data(
    group_call,
    length,
):

    if length <= 0:
        return b""

    with playback_lock:

        if not playback_buffer:

            return b"\x00" * length

        data = bytes(
            playback_buffer[:length]
        )

        del playback_buffer[
            :length
        ]

    if len(data) < length:

        data += b"\x00" * (
            length - len(data)
        )

    return data


# ============================================================
# INCOMING AUDIO CALLBACK
# ============================================================

def raw_recorded_callback(
    group_call,
    frame,
    length,
):

    global MAIN_LOOP

    if not frame:
        return

    if length:

        frame = frame[:length]

    if MAIN_LOOP is None:
        return

    try:

        future = (
            asyncio.run_coroutine_threadsafe(
                voice_engine.handle_frame(
                    frame,
                    handle_kriti_trigger,
                ),
                MAIN_LOOP,
            )
        )

        # We intentionally do not wait here.
        # The PyTgCalls native audio thread
        # must remain free.

    except Exception as error:

        print(
            f"[Voice Callback Error] {error}"
        )


# ============================================================
# GROUP CALL
# ============================================================

group_call = GroupCallFactory(
    user_client
).get_raw_group_call(
    on_played_data=on_played_data,
    on_recorded_data=raw_recorded_callback,
)


# ============================================================
# VOICE MAPPING
# ============================================================

VOICE_MAPPING = {

    "hi": "hi-IN-SwaraNeural",

    "en": "en-IN-NeerjaNeural",

    "bn": "bn-IN-TanishaaNeural",

    "ta": "ta-IN-PallaviNeural",

    "te": "te-IN-ShrutiNeural",

    "mr": "mr-IN-AarohiNeural",

    "gu": "gu-IN-DhwaniNeural",

    "default": "hi-IN-SwaraNeural",
}


# ============================================================
# START MESSAGE
# ============================================================

START_TEXT = """
<b>✨ Hello! I'm Kriti AI VC Bot</b>

🤖 I am an AI-powered Telegram Voice Chat bot.

🎙 Add me to your group and let the user account join the Voice Chat.

🧠 I automatically listen to the Voice Chat.

💬 Say:

<b>Hello Kriti</b>
<b>Hey Kriti</b>
<b>Hi Kriti</b>

or simply

<b>Kriti</b>

Kriti will understand your speech using Gemini AI and automatically reply with her voice.

🧠 Powered by Gemini AI
🔊 Multilingual Voice Support

Press the button below to see all commands.
"""


# ============================================================
# HELP
# ============================================================

HELP_TEXT = """
<b>📚 Kriti AI VC Bot — Help & Commands</b>


<b>🎙 Join Voice Chat</b>

<code>/joinvc @groupusername</code>

Kriti's user account will join the Voice Chat of the specified group.

Example:

<code>/joinvc @mygroup</code>

You can also use:

<code>/joinvc https://t.me/mygroup</code>


<b>👋 Leave Voice Chat</b>

<code>/leavevc</code>

Use this inside the group to make Kriti leave the current Voice Chat.


<b>🤖 Automatic AI Conversation</b>

There is NO <code>/speak</code> command.

After Kriti joins the Voice Chat, she automatically listens.

Say:

• Hello Kriti
• Hey Kriti
• Hi Kriti
• Kriti

Then speak your message.

Kriti will:

🎙 Listen
⬇️
📝 Gemini converts speech to text
⬇️
🧠 Gemini AI generates a response
⬇️
🔊 Edge TTS generates voice
⬇️
🎙 Kriti speaks back in the Voice Chat


<b>🌐 Supported Languages</b>

🇮🇳 Hindi

🇬🇧 English

🇧🇩 Bengali

🇮🇳 Tamil

🇮🇳 Telugu

🇮🇳 Marathi

🇮🇳 Gujarati

Hindi / Hinglish is supported as well.


<b>👑 Creator</b>

If someone asks who created Kriti, the AI will reply:

<code>मुझे बनाने वाले मिस्टर बादल सर हैं।</code>


<b>⚠️ Required</b>

• Valid user session
• User account must have access to the group
• Voice Chat must be active
• GEMINI_API_KEY must be valid
"""


# ============================================================
# TEXT TO SPEECH
# ============================================================

async def generate_speech(
    text: str,
    voice_code: str = "hi-IN-SwaraNeural",
    output_path: str = "output.mp3",
) -> str:

    communicate = edge_tts.Communicate(
        text,
        voice_code,
    )

    await communicate.save(
        output_path
    )

    return output_path


# ============================================================
# MP3 → RAW PCM
# ============================================================

def mp3_to_pcm(
    file_path: str,
) -> bytes:

    output = bytearray()

    container = av.open(
        file_path
    )

    try:

        audio_stream = None

        for stream in container.streams:

            if stream.type == "audio":

                audio_stream = stream

                break

        if audio_stream is None:

            raise RuntimeError(
                "No audio stream found."
            )

        resampler = (
            av.audio.resampler.AudioResampler(
                format="s16",
                layout="stereo",
                rate=48000,
            )
        )

        for frame in container.decode(
            audio=0
        ):

            converted_frames = (
                resampler.resample(
                    frame
                )
            )

            for converted in converted_frames:

                for plane in converted.planes:

                    output.extend(
                        bytes(plane)
                    )

        # Flush resampler

        converted_frames = (
            resampler.resample(None)
        )

        for converted in converted_frames:

            for plane in converted.planes:

                output.extend(
                    bytes(plane)
                )

    finally:

        container.close()

    return bytes(output)


# ============================================================
# QUEUE AUDIO
# ============================================================

async def queue_audio(
    file_path: str,
):

    global playback_buffer

    pcm_data = await asyncio.to_thread(
        mp3_to_pcm,
        file_path,
    )

    if not pcm_data:

        raise RuntimeError(
            "Converted PCM audio is empty."
        )

    with playback_lock:

        playback_buffer.extend(
            pcm_data
        )

    print(
        f"[Audio] Added {len(pcm_data)} bytes to playback buffer."
    )


# ============================================================
# WAIT FOR PLAYBACK
# ============================================================

async def wait_for_playback():

    while True:

        with playback_lock:

            remaining = len(
                playback_buffer
            )

        if remaining <= 0:

            break

        await asyncio.sleep(
            0.1
        )

    await asyncio.sleep(
        0.35
    )


# ============================================================
# GEMINI RESPONSE
# ============================================================

async def generate_multilingual_response(
    user_name: str,
    user_speech: str,
) -> tuple[str, str]:

    prompt = f"""
You are Kriti, a friendly Indian AI girl
participating in a Telegram Voice Chat.

The user speaking to you is:

{user_name}

The user said:

{user_speech}


IMPORTANT INSTRUCTIONS:


1. CREATOR QUESTION

If the user asks:

Who created you?
Who made you?
Who is your owner?
Who is your boss?
Who developed you?

You MUST mention exactly:

मुझे बनाने वाले मिस्टर बादल सर हैं।


2. LANGUAGE

Detect the language of the user.

Reply in the same language.

Supported:

Hindi
English
Bengali
Tamil
Telugu
Marathi
Gujarati
Hinglish


3. USER NAME

Address the user naturally by their name when appropriate.


4. RESPONSE LENGTH

Keep the response short and natural.

Maximum 1-2 sentences.


5. OUTPUT FORMAT

Return EXACTLY:

LANG_CODE | Response


Supported language codes:

hi
en
bn
ta
te
mr
gu
"""

    try:

        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
        )

        raw_output = (
            response.text.strip()
            if response.text
            else ""
        )

    except Exception as error:

        print(
            f"[Gemini Error] {error}"
        )

        return (
            "hi",
            f"{user_name}, अभी AI response में problem आ गई है।",
        )

    if not raw_output:

        return (
            "hi",
            f"{user_name}, अभी मुझे response नहीं मिला।",
        )

    if "|" in raw_output:

        lang_code, response_text = (
            raw_output.split(
                "|",
                1,
            )
        )

        lang_code = (
            lang_code.strip().lower()
        )

        response_text = (
            response_text.strip()
        )

        return (
            lang_code,
            response_text,
        )

    return (
        "hi",
        raw_output,
    )


# ============================================================
# AUTOMATIC KRITI RESPONSE
# ============================================================

async def handle_kriti_trigger(
    user_speech: str,
):

    global is_kriti_speaking

    if is_kriti_speaking:

        return

    if not current_vc_chat_id:

        return

    is_kriti_speaking = True

    print(
        f"[Kriti Trigger] {user_speech}"
    )

    voice_engine.pause()

    try:

        # Stop listening while Kriti speaks

        try:

            group_call.pause_recording()

        except Exception:

            pass


        # ----------------------------------------------------
        # Gemini AI response
        # ----------------------------------------------------

        user_name = "Friend"

        lang_code, ai_text = (
            await generate_multilingual_response(
                user_name,
                user_speech,
            )
        )

        if not ai_text:

            return

        print(
            f"[Kriti Response] {ai_text}"
        )


        # ----------------------------------------------------
        # Select TTS voice
        # ----------------------------------------------------

        voice = VOICE_MAPPING.get(
            lang_code,
            VOICE_MAPPING["default"],
        )


        # ----------------------------------------------------
        # Generate TTS
        # ----------------------------------------------------

        timestamp = int(
            time.time() * 1000
        )

        response_file = (
            f"kriti_response_{timestamp}.mp3"
        )

        await generate_speech(
            ai_text,
            voice,
            response_file,
        )


        # ----------------------------------------------------
        # Add audio to VC
        # ----------------------------------------------------

        await queue_audio(
            response_file
        )


        # ----------------------------------------------------
        # Wait until Kriti finishes speaking
        # ----------------------------------------------------

        await wait_for_playback()


        # ----------------------------------------------------
        # Delete temporary response
        # ----------------------------------------------------

        try:

            if os.path.exists(
                response_file
            ):

                os.remove(
                    response_file
                )

        except Exception:

            pass


    except Exception as error:

        print(
            f"[Kriti Voice Error] {error}"
        )


    finally:

        is_kriti_speaking = False

        try:

            group_call.resume_recording()

        except Exception:

            pass

        voice_engine.resume()

        print(
            "[Kriti] Listening again..."
        )


# ============================================================
# /START
# ============================================================

@bot_client.on_message(
    filters.command("start")
)
async def start_command(
    client,
    message,
):

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📚 Help & Commands",
                    callback_data="help_commands",
                )
            ]
        ]
    )

    await message.reply_text(
        START_TEXT,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


# ============================================================
# HELP BUTTON
# ============================================================

@bot_client.on_callback_query(
    filters.regex("^help_commands$")
)
async def help_callback(
    client,
    callback_query,
):

    await callback_query.answer()

    try:

        await callback_query.message.edit_text(
            HELP_TEXT,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back",
                            callback_data="back_start",
                        )
                    ]
                ]
            ),
            disable_web_page_preview=True,
        )

    except Exception as error:

        print(
            f"[Help Error] {error}"
        )


# ============================================================
# BACK BUTTON
# ============================================================

@bot_client.on_callback_query(
    filters.regex("^back_start$")
)
async def back_start(
    client,
    callback_query,
):

    await callback_query.answer()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📚 Help & Commands",
                    callback_data="help_commands",
                )
            ]
        ]
    )

    try:

        await callback_query.message.edit_text(
            START_TEXT,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    except Exception as error:

        print(
            f"[Back Error] {error}"
        )


# ============================================================
# /JOINVC
# ============================================================

@bot_client.on_message(
    filters.command("joinvc")
)
async def join_voice_chat(
    client,
    message,
):

    global current_vc_chat_id

    try:

        if len(message.command) < 2:

            await message.reply_text(
                "❌ <b>Usage:</b>\n\n"
                "<code>/joinvc @groupusername</code>\n\n"
                "or\n\n"
                "<code>/joinvc https://t.me/group</code>"
            )

            return


        chat_identifier = (
            message.command[1]
        )


        status_message = (
            await message.reply_text(
                "🔄 <b>Connecting to Voice Chat...</b>"
            )
        )


        target_chat = (
            await user_client.get_chat(
                chat_identifier
            )
        )


        chat_id = target_chat.id


        # ----------------------------------------------------
        # Join Voice Chat
        # ----------------------------------------------------

        await group_call.start(
            chat_id
        )


        current_vc_chat_id = chat_id


        # ----------------------------------------------------
        # Welcome voice
        # ----------------------------------------------------

        welcome_file = (
            "welcome.mp3"
        )

        try:

            if not os.path.exists(
                welcome_file
            ):

                await generate_speech(
                    "Hello everyone! I am Kriti. I am ready to talk with you.",
                    VOICE_MAPPING["en"],
                    welcome_file,
                )

            await queue_audio(
                welcome_file
            )

            await wait_for_playback()

        except Exception as audio_error:

            print(
                f"[Welcome Audio Error] {audio_error}"
            )


        # ----------------------------------------------------
        # Start listening
        # ----------------------------------------------------

        try:

            group_call.resume_recording()

        except Exception:

            pass

        voice_engine.resume()


        await status_message.edit_text(
            f"✅ <b>Successfully joined Voice Chat!</b>\n\n"
            f"🎙 <b>Group:</b> {target_chat.title}\n\n"
            f"🤖 <b>Kriti AI is ready.</b>\n\n"
            f"Say <b>Hello Kriti</b>, "
            f"<b>Hey Kriti</b>, "
            f"<b>Hi Kriti</b> "
            f"or simply <b>Kriti</b> "
            f"to start talking."
        )


    except Exception as error:

        print(
            f"[Join VC Error] {error}"
        )

        await message.reply_text(
            f"❌ <b>Error joining VC:</b>\n\n"
            f"<code>{error}</code>"
        )


# ============================================================
# /LEAVEVC
# ============================================================

@bot_client.on_message(
    filters.command("leavevc")
)
async def leave_voice_chat(
    client,
    message,
):

    global current_vc_chat_id

    try:

        voice_engine.pause()

        try:

            group_call.pause_recording()

        except Exception:

            pass


        await group_call.stop()


        current_vc_chat_id = None


        with playback_lock:

            playback_buffer.clear()


        voice_engine.resume()


        await message.reply_text(
            "👋 <b>Left the Voice Chat!</b>"
        )


    except Exception as error:

        print(
            f"[Leave VC Error] {error}"
        )

        await message.reply_text(
            f"❌ <b>Error leaving VC:</b>\n\n"
            f"<code>{error}</code>"
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    global MAIN_LOOP

    MAIN_LOOP = asyncio.get_running_loop()


    print(
        "=========================================="
    )

    print(
        "Starting Kriti AI VC Bot..."
    )

    print(
        "=========================================="
    )


    # --------------------------------------------------------
    # Start user account
    # --------------------------------------------------------

    await user_client.start()

    print(
        "✅ User account started."
    )


    # --------------------------------------------------------
    # Start bot
    # --------------------------------------------------------

    await bot_client.start()

    print(
        "✅ Bot account started."
    )


    print(
        "=========================================="
    )

    print(
        "🤖 Kriti AI Automatic Voice Chat Bot"
    )

    print(
        "🎙 Voice detection: ACTIVE"
    )

    print(
        "🧠 Gemini STT: ACTIVE"
    )

    print(
        "🧠 Gemini AI: ACTIVE"
    )

    print(
        "🔊 Edge TTS: ACTIVE"
    )

    print(
        "=========================================="
    )

    print(
        "Waiting for:"
    )

    print(
        "Hello Kriti / Hey Kriti / Hi Kriti / Kriti"
    )

    print(
        "=========================================="
    )


    await asyncio.Event().wait()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
