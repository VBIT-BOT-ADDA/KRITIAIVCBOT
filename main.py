```python
import os
import asyncio
import edge_tts

from google import genai

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from pytgcalls import GroupCallFactory

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    GEMINI_API_KEY,
)


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
# PYTGCALLS
# Compatible with pytgcalls==3.0.0.dev24
# ============================================================

group_call = GroupCallFactory(
    user_client
).get_file_group_call(
    play_on_repeat=False
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

🎙 I can join your group's Voice Chat and speak AI-generated responses using multilingual text-to-speech.

🧠 Powered by Gemini AI
🔊 Multilingual Voice Support

Press the button below to see all commands and how to use me.
"""


# ============================================================
# HELP MESSAGE
# ============================================================

HELP_TEXT = """
<b>📚 Kriti AI VC Bot — Help & Commands</b>

<b>🎙 Voice Chat Commands</b>

<code>/joinvc @username</code>
Join the Voice Chat of the specified group.

Example:
<code>/joinvc @mygroup</code>

You can also use a Telegram link:
<code>/joinvc https://t.me/mygroup</code>


<code>/leavevc</code>
Leave the Voice Chat of the current group.

Example:
Send <code>/leavevc</code> inside the group.


<b>🗣 AI Speaking</b>

<code>/speak Your message</code>

Kriti will understand the message using Gemini AI, detect the requested language and generate a voice response.

Example:

<code>/speak Hello everyone</code>

or

<code>/speak नमस्ते दोस्तों</code>


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


<b>⚠️ Important</b>

• The user account session must be valid.
• The user account must have access to the target group.
• The bot should be added to the group.
• The Voice Chat must be available.
• For /speak, a valid GEMINI_API_KEY is required.
"""


# ============================================================
# TTS
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

    await communicate.save(output_path)

    return output_path


# ============================================================
# GEMINI RESPONSE
# ============================================================

async def generate_multilingual_response(
    user_name: str,
    user_speech: str,
) -> tuple[str, str]:

    prompt = (
        f"You are a friendly, expressive Indian girl named "
        f"'Pari' or 'Kriti' participating in a Telegram Voice Chat.\n\n"

        f"The user speaking to you is named: {user_name}\n"
        f"User said: {user_speech}\n\n"

        f"Instructions:\n"

        f"1. CREATOR/OWNER QUESTION:\n"
        f"If the user asks who created you, who made you, "
        f"who your owner is, or who your boss is, "
        f"strictly mention:\n"
        f"'मुझे बनाने वाले मिस्टर बादल सर हैं।'\n\n"

        f"2. Detect the language spoken or requested by the user.\n\n"

        f"3. Reply in the same language or requested language.\n\n"

        f"4. Always address the user by their name: {user_name}\n\n"

        f"5. Keep the response natural, friendly and short.\n"
        f"Maximum 1-2 sentences.\n\n"

        f"6. Return EXACTLY this format:\n"
        f"LANG_CODE | Response text\n\n"

        f"Supported language codes:\n"
        f"hi, en, bn, ta, te, mr, gu"
    )

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
            f"{user_name}, अभी AI response में problem आ गई है।"
        )

    if not raw_output:

        return (
            "hi",
            f"{user_name}, अभी मुझे response नहीं मिला।"
        )

    if "|" in raw_output:

        lang_code, response_text = raw_output.split(
            "|",
            1
        )

        lang_code = lang_code.strip().lower()
        response_text = response_text.strip()

        return (
            lang_code,
            response_text
        )

    return (
        "hi",
        raw_output
    )


# ============================================================
# START COMMAND
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
                    callback_data="help_commands"
                )
            ]
        ]
    )

    await message.reply_text(
        START_TEXT,
        reply_markup=keyboard,
        disable_web_page_preview=True
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
                            callback_data="back_start"
                        )
                    ]
                ]
            ),
            disable_web_page_preview=True
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
                    callback_data="help_commands"
                )
            ]
        ]
    )

    try:

        await callback_query.message.edit_text(
            START_TEXT,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    except Exception as error:

        print(
            f"[Back Error] {error}"
        )


# ============================================================
# /joinvc
# ============================================================

@bot_client.on_message(
    filters.command("joinvc")
)
async def join_voice_chat(
    client,
    message,
):

    try:

        if len(message.command) < 2:

            await message.reply_text(
                "❌ <b>Usage:</b>\n\n"
                "<code>/joinvc @groupusername</code>\n\n"
                "or\n\n"
                "<code>/joinvc https://t.me/group</code>"
            )

            return

        chat_identifier = message.command[1]

        status_message = await message.reply_text(
            "🔄 <b>Connecting to Voice Chat...</b>"
        )

        target_chat = await user_client.get_chat(
            chat_identifier
        )

        chat_id = target_chat.id

        # Create welcome audio
        welcome_file = "welcome.mp3"

        if not os.path.exists(welcome_file):

            await generate_speech(
                "Hello everyone! I am Kriti. I am ready to talk with you.",
                VOICE_MAPPING["en"],
                welcome_file
            )

        # Start / join voice chat
        await group_call.start(
            chat_id
        )

        # Play welcome audio
        try:

            await group_call.start_audio(
                welcome_file
            )

        except Exception as audio_error:

            print(
                f"[Welcome Audio Error] {audio_error}"
            )

        await status_message.edit_text(
            f"✅ <b>Successfully joined Voice Chat!</b>\n\n"
            f"🎙 <b>Group:</b> {target_chat.title}\n\n"
            f"🤖 Kriti AI is ready.\n"
            f"Use <code>/speak your message</code> to make me speak."
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
# /leavevc
# ============================================================

@bot_client.on_message(
    filters.command("leavevc")
)
async def leave_voice_chat(
    client,
    message,
):

    try:

        await group_call.stop(
            message.chat.id
        )

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
# /speak
# ============================================================

@bot_client.on_message(
    filters.command("speak")
)
async def speak_command(
    client,
    message,
):

    try:

        if len(message.command) < 2:

            await message.reply_text(
                "❌ <b>Usage:</b>\n\n"
                "<code>/speak Your message</code>"
            )

            return

        user_name = (
            message.from_user.first_name
            if message.from_user
            else "Friend"
        )

        user_text = message.text.split(
            " ",
            1
        )[1].strip()

        processing_message = await message.reply_text(
            "🧠 <b>Kriti is thinking...</b>"
        )

        # Gemini response
        lang_code, ai_text = (
            await generate_multilingual_response(
                user_name,
                user_text
            )
        )

        voice = VOICE_MAPPING.get(
            lang_code,
            VOICE_MAPPING["default"]
        )

        response_file = (
            f"response_{message.id}.mp3"
        )

        # Generate TTS
        await generate_speech(
            ai_text,
            voice,
            response_file
        )

        # Start audio in VC
        await group_call.start_audio(
            response_file
        )

        await processing_message.edit_text(
            f"🗣 <b>Kriti:</b>\n\n"
            f"{ai_text}"
        )

        # Clean generated audio after playback starts
        asyncio.create_task(
            cleanup_file(
                response_file,
                30
            )
        )

    except Exception as error:

        print(
            f"[Speak Error] {error}"
        )

        try:

            await message.reply_text(
                f"❌ <b>Error playing voice response:</b>\n\n"
                f"<code>{error}</code>"
            )

        except Exception:
            pass


# ============================================================
# CLEANUP
# ============================================================

async def cleanup_file(
    file_path: str,
    delay: int = 30
):

    try:

        await asyncio.sleep(
            delay
        )

        if os.path.exists(file_path):

            os.remove(
                file_path
            )

    except Exception as error:

        print(
            f"[Cleanup Error] {error}"
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "Starting Kriti AI VC Bot..."
    )

    await user_client.start()

    print(
        "User account started."
    )

    await bot_client.start()

    print(
        "Bot account started."
    )

    print(
        "Kriti AI Multilingual Voice Chatbot is active!"
    )

    await asyncio.Event().wait()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
```
