import os
import asyncio
import edge_tts

from google import genai

from pyrogram import Client, filters
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    GEMINI_API_KEY,
)


# ==============================
# Configure Gemini AI
# ==============================

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL = "gemini-3.5-flash"


# ==============================
# Initialize Clients
# ==============================

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

vc_app = PyTgCalls(user_client)


# ==============================
# Multilingual TTS Mapping
# ==============================

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


# ==============================
# Generate Speech
# ==============================

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


# ==============================
# Gemini AI Response
# ==============================

async def generate_multilingual_response(
    user_name: str,
    user_speech: str,
) -> tuple[str, str]:

    prompt = (
        f"You are a friendly, expressive Indian girl named 'Pari' "
        f"(or 'Kriti') participating in a Telegram Voice Chat. "
        f"The user speaking to you is named '{user_name}'. "
        f"User said: '{user_speech}'. "

        f"Instructions:\n"

        f"1. CREATOR/OWNER QUESTION: "
        f"If the user asks who created you, who made you, "
        f"or who your owner/boss is "
        f"(e.g., 'तुम्हें किसने बनाया', "
        f"'तुम्हारा ओनर कौन है', 'Who made you'), "
        f"strictly reply mentioning: "
        f"'मुझे बनाने वाले मिस्टर बादल सर हैं।'\n"

        f"2. Automatically detect the language requested "
        f"or spoken by the user "
        f"(e.g., Hindi, English, Hinglish, Bengali, Tamil, etc.).\n"

        f"3. Reply in the exact same language or the language "
        f"requested. For example, if the user says "
        f"'Talk in English', switch to English.\n"

        f"4. Always address the user by their name "
        f"('{user_name}') in the response.\n"

        f"5. Keep the response natural, warm, conversational, "
        f"and short (1-2 sentences maximum).\n"

        f"6. Return output format EXACTLY as:\n"
        f"LANG_CODE | Your response text\n"

        f"Examples of LANG_CODE: "
        f"hi (Hindi/Hinglish), "
        f"en (English), "
        f"bn (Bengali), "
        f"ta (Tamil), "
        f"te (Telugu), "
        f"mr (Marathi), "
        f"gu (Gujarati)."
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
            else "माफ़ करना, अभी मैं जवाब नहीं दे पा रही हूँ।"
        )

    except Exception as error:

        print(f"Gemini Error: {error}")

        return (
            "hi",
            f"{user_name}, अभी AI response में थोड़ी problem आ गई है।",
        )

    if "|" in raw_output:

        lang_code, response_text = raw_output.split(
            "|",
            1,
        )

        return (
            lang_code.strip().lower(),
            response_text.strip(),
        )

    return "hi", raw_output


# ==============================
# /joinvc
# ==============================

@bot_client.on_message(filters.command("joinvc"))
async def join_voice_chat(
    client,
    message,
):

    try:

        if len(message.command) < 2:

            return await message.reply_text(
                "Usage: `/joinvc @group_username` "
                "or `/joinvc https://t.me/...`"
            )

        chat_identifier = message.command[1]

        target_chat = await user_client.get_chat(
            chat_identifier
        )

        # Initial dummy stream setup
        if not os.path.exists("welcome.mp3"):

            await generate_speech(
                "Hello everyone! I am ready.",
                VOICE_MAPPING["en"],
                "welcome.mp3",
            )

        await vc_app.join_group_call(
            target_chat.id,
            AudioPiped("welcome.mp3"),
        )

        await message.reply_text(
            f"Successfully joined Voice Chat in "
            f"**{target_chat.title}**!"
        )

    except Exception as error:

        await message.reply_text(
            f"Error joining VC: {str(error)}"
        )


# ==============================
# /leavevc
# ==============================

@bot_client.on_message(filters.command("leavevc"))
async def leave_voice_chat(
    client,
    message,
):

    try:

        await vc_app.leave_group_call(
            message.chat.id
        )

        await message.reply_text(
            "Left the Voice Chat!"
        )

    except Exception as error:

        await message.reply_text(
            f"Error leaving VC: {str(error)}"
        )


# ==============================
# /speak
# ==============================

@bot_client.on_message(filters.command("speak"))
async def speak_command(
    client,
    message,
):

    try:

        if len(message.command) < 2:

            return await message.reply_text(
                "Usage: `/speak <your message>`"
            )

        user_name = (
            message.from_user.first_name
            if message.from_user
            else "Friend"
        )

        user_text = message.text.split(
            " ",
            1,
        )[1]

        # Get AI Response & Language Code
        lang_code, ai_text = (
            await generate_multilingual_response(
                user_name,
                user_text,
            )
        )

        # Select TTS Voice
        voice = VOICE_MAPPING.get(
            lang_code,
            VOICE_MAPPING["default"],
        )

        # Generate Audio File
        audio_file = await generate_speech(
            ai_text,
            voice,
            "response.mp3",
        )

        # Play audio in VC
        await vc_app.change_stream(
            message.chat.id,
            AudioPiped(audio_file),
        )

        await message.reply_text(
            f"**Kriti:** {ai_text}"
        )

    except Exception as error:

        await message.reply_text(
            f"Error playing voice response: {str(error)}"
        )


# ==============================
# Main
# ==============================

async def main():

    await user_client.start()

    await bot_client.start()

    await vc_app.start()

    print(
        "AI Multilingual Voice Chatbot is active!"
    )

    await asyncio.Event().wait()


# ==============================
# Run
# ==============================

if __name__ == "__main__":

    asyncio.run(main())
