import os
import asyncio
import threading
import time
import random

# Pyrogram 2.0.106 has an old peer-id range check which can reject valid
# modern Telegram supergroup IDs such as -1002299770478.
# Patch the helper before starting either client.
import pyrogram.utils as pyrogram_utils


# Pyrogram 2.0.106 still uses old 32-bit peer-id boundaries.
# Modern Telegram supergroups can have marked IDs such as
# -1002299770478, so patch BOTH the constants and the helper.
# The constant patch is important because some Pyrogram internals
# reference the module-level ranges directly.
pyrogram_utils.MIN_CHANNEL_ID = -10**18
pyrogram_utils.MAX_CHANNEL_ID = -10**12
pyrogram_utils.MIN_CHAT_ID = -10**18
pyrogram_utils.MAX_USER_ID_OLD = 10**18
pyrogram_utils.MAX_USER_ID = 10**18


def _fixed_get_peer_type(peer_id: int) -> str:
    peer_id = int(peer_id)

    if peer_id < 0:
        # Telegram marked channel/supergroup IDs use the -100... form.
        if str(peer_id).startswith("-100"):
            return "channel"

        return "chat"

    if peer_id > 0:
        return "user"

    raise ValueError(f"Peer id invalid: {peer_id}")


pyrogram_utils.get_peer_type = _fixed_get_peer_type

import av
import edge_tts

from google import genai

from pyrogram import Client, filters
from pyrogram.raw import functions
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

# Every user is allowed to use /joinvc and /leavevc.
# The configured SESSION_STRING user is shared, so operations are
# serialized to prevent two users from changing the VC at the same time.
vc_operation_lock = asyncio.Lock()

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
<b>✅ BOT STARTED SUCCESSFULLY</b>

<b>✨ Hello! I'm Kriti AI VC Bot</b>

🤖 I am an AI-powered Telegram Voice Chat bot.

🎙 Send /joinvc from the bot DM and let the configured user session join the group Voice Chat.

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

<b>✅ Commands available to ALL users</b>

<b>1️⃣ /start</b>
Starts the bot and shows this Help & Commands button.

<b>2️⃣ /joinvc</b>
Makes the configured SESSION_STRING user account join the target group and connect to its already-active Voice Chat.

<b>Usage:</b>
<code>/joinvc @groupusername</code>

<code>/joinvc https://t.me/group</code>

<code>/joinvc https://t.me/+PRIVATE_INVITE</code>

You can send this command directly in Kriti's DM.
The bot itself does <b>NOT</b> need to be a member or admin of the target group.
No admin check is performed for the user who sends the command.

<b>3️⃣ /leavevc</b>
Disconnects the configured SESSION_STRING user account from the current Voice Chat.

<b>Usage:</b>
<code>/leavevc</code>

<b>🎙 Automatic AI Conversation</b>

There is NO <code>/speak</code> command.
After Kriti joins an active Voice Chat, she automatically listens.

Say:
• <b>Hello Kriti</b>
• <b>Hey Kriti</b>
• <b>Hi Kriti</b>
• <b>Kriti</b>

Then speak normally.

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

<b>⚠️ Important</b>

• All users can use <code>/joinvc</code> and <code>/leavevc</code>.
• The bot does not need to be added/admin in the target group.
• The configured SESSION_STRING account must be able to join the group.
• The target Voice Chat should already be active.
• Creating a brand-new Voice Chat requires Telegram's manage-call permission, so this bot does not try to bypass that permission.
• <code>GEMINI_API_KEY</code> must be valid.
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


# ============================================================
# GROUP LINK / VOICE CHAT HELPERS
# ============================================================

def normalize_group_input(value: str) -> tuple[str, bool]:
    """
    Returns:
        (normalized_value, is_private_invite)

    Supported:
        @username
        username
        https://t.me/username
        https://telegram.me/username
        https://t.me/+invite_hash
        https://t.me/joinchat/invite_hash
    """
    value = (value or "").strip().rstrip("/")

    if not value:
        raise ValueError("Group link/username is empty.")

    lower = value.lower()

    is_private_invite = (
        "t.me/+" in lower
        or "telegram.me/+" in lower
        or "t.me/joinchat/" in lower
        or "telegram.me/joinchat/" in lower
    )

    if is_private_invite:
        return value.split("?", 1)[0], True

    prefixes = (
        "https://t.me/",
        "http://t.me/",
        "https://telegram.me/",
        "http://telegram.me/",
    )

    for prefix in prefixes:
        if lower.startswith(prefix):
            value = value[len(prefix):]
            break

    # A public Telegram username link must not be confused with
    # a message link such as t.me/c/123/456.
    value = value.split("?", 1)[0].split("/", 1)[0]
    value = value.lstrip("@").strip()

    if not value:
        raise ValueError("Invalid Telegram group username/link.")

    if value == "c":
        raise ValueError(
            "This is a Telegram message link, not a group invite link. "
            "Use the group's public @username or a private invite link."
        )

    return value, False


async def join_target_group(group_input: str):
    """
    IMPORTANT:
    This uses USER_SESSION (user_client), NOT bot_client.

    Therefore the bot itself does NOT need to be a member/admin of
    the target group. The logged-in user session joins the group.
    """
    normalized, is_private_invite = normalize_group_input(group_input)

    if is_private_invite:
        try:
            chat = await user_client.join_chat(normalized)
            return chat
        except Exception as error:
            error_text = str(error).upper()

            if "USER_ALREADY_PARTICIPANT" in error_text:
                # The account is already inside. Resolve the invite
                # through the user session.
                try:
                    return await user_client.get_chat(normalized)
                except Exception:
                    raise RuntimeError(
                        "The user account is already a member, but Telegram "
                        "could not resolve this invite link. Send the "
                        "group's public @username if it has one."
                    )

            if "INVITE_REQUEST_SENT" in error_text:
                raise RuntimeError(
                    "This invite requires admin approval. "
                    "The user account has sent a join request, so Kriti "
                    "cannot enter the Voice Chat until the request is approved."
                )

            raise

    # Public username / public t.me link.
    try:
        chat = await user_client.join_chat(normalized)
        return chat
    except Exception as error:
        error_text = str(error).upper()

        # Already joined is not an error for our purpose.
        if (
            "USER_ALREADY_PARTICIPANT" in error_text
            or "ALREADY_PARTICIPANT" in error_text
            or "ALREADY PARTICIPANT" in error_text
        ):
            return await user_client.get_chat(normalized)

        # Some Telegram/Pyrogram versions expose the already-member
        # condition with a different text. Resolve the username as a
        # safe fallback, then check whether it is accessible.
        try:
            chat = await user_client.get_chat(normalized)
            return chat
        except Exception:
            raise


async def create_voice_chat_if_needed(chat_id: int):
    """
    If no Voice Chat is currently active, ask Telegram to create one
    using the USER ACCOUNT.

    Creating a Voice Chat requires the user session to have the
    necessary group permissions. If an active VC already exists,
    Telegram may return GROUPCALL_ALREADY_EXISTS; that is harmless.
    """
    peer = await user_client.resolve_peer(chat_id)

    try:
        await user_client.invoke(
            functions.phone.CreateGroupCall(
                peer=peer,
                random_id=random.randint(1, 2147483647),
                title="Kriti AI Voice Chat",
            )
        )
        print(f"[VC] CreateGroupCall requested for {chat_id}")
    except Exception as error:
        error_text = str(error).upper()

        if "GROUPCALL_ALREADY_EXISTS" in error_text:
            print("[VC] Voice Chat already exists.")
            return

        # Some Telegram installations use slightly different wording.
        # If the error says a call already exists, continue to PyTgCalls.
        if "GROUP CALL ALREADY EXISTS" in error_text:
            print("[VC] Voice Chat already exists.")
            return

        raise


async def start_user_voice_chat(chat_id: int):
    """
    Join an already-active Voice Chat with the configured USER SESSION.

    IMPORTANT:
    No admin rights are requested or checked here.

    Telegram requires the manage_call admin right to CREATE a new
    Voice Chat. Therefore this bot does not try to create a new VC
    automatically. A Voice Chat must already be active; then the
    SESSION_STRING account attempts to join it.
    """
    try:
        await group_call.start(chat_id)
        return
    except Exception as error:
        error_text = str(error)

        if (
            "GROUPCALL_INVALID" in error_text.upper()
            or "GROUPCALL_FORBIDDEN" in error_text.upper()
            or "GROUPCALL_JOIN_MISSING" in error_text.upper()
        ):
            raise RuntimeError(
                "No usable active Voice Chat was found. "
                "Please start the group's Voice Chat first. "
                "Kriti does not require admin rights to join an already-active VC."
            ) from error

        raise


@bot_client.on_message(
    filters.command("joinvc")
)
async def join_voice_chat(
    client,
    message,
):
    """
    /joinvc is intentionally available to ALL users.

    The command may be sent in the bot's DM or any chat where the bot
    can receive the command. The bot itself does NOT need to be a
    member/admin of the target group.

    The actual group join and VC connection are performed by the
    configured SESSION_STRING user account.
    """

    global current_vc_chat_id

    async with vc_operation_lock:
        status_message = None

        try:
            if len(message.command) < 2:
                await message.reply_text(
                    "❌ <b>Usage:</b>\n\n"
                    "<code>/joinvc @groupusername</code>\n\n"
                    "or\n\n"
                    "<code>/joinvc https://t.me/group</code>\n\n"
                    "or a private invite:\n\n"
                    "<code>/joinvc https://t.me/+PRIVATE_INVITE</code>\n\n"
                    "ℹ️ <b>No admin is required for the bot.</b>\n"
                    "The configured SESSION_STRING user account joins the "
                    "group and connects to an already-active Voice Chat."
                )
                return

            # Anyone can send this command. The bot does not need to be
            # present in the target group.
            group_input = message.command[1].strip()

            status_message = await message.reply_text(
                "🔄 <b>Processing group link...</b>\n\n"
                "👤 The configured user session is joining/resolving the group."
            )

            # --------------------------------------------------------
            # JOIN / RESOLVE TARGET GROUP WITH USER SESSION
            # --------------------------------------------------------

            target_chat = await join_target_group(group_input)

            if not target_chat:
                raise RuntimeError(
                    "Telegram did not return the target group."
                )

            chat_id = int(target_chat.id)
            chat_title = getattr(
                target_chat,
                "title",
                None,
            ) or "Telegram Group"

            print(
                f"[JoinVC] Target={chat_title!r} "
                f"ID={chat_id} "
                f"TYPE={getattr(target_chat, 'type', '')}"
            )

            await status_message.edit_text(
                f"✅ <b>Group joined/resolved.</b>\n\n"
                f"🎙 <b>Group:</b> {chat_title}\n"
                f"🆔 <code>{chat_id}</code>\n\n"
                f"🔄 <b>Connecting to the active Voice Chat...</b>"
            )

            # --------------------------------------------------------
            # STOP PREVIOUS VC
            # --------------------------------------------------------

            if current_vc_chat_id is not None:
                try:
                    voice_engine.pause()
                except Exception:
                    pass

                try:
                    group_call.pause_recording()
                except Exception:
                    pass

                try:
                    await group_call.stop()
                except Exception as stop_error:
                    print(
                        f"[Old VC Stop] {stop_error}"
                    )

                current_vc_chat_id = None

                with playback_lock:
                    playback_buffer.clear()

                await asyncio.sleep(0.5)

            # --------------------------------------------------------
            # JOIN ACTIVE VC
            # --------------------------------------------------------

            await start_user_voice_chat(chat_id)

            current_vc_chat_id = chat_id

            # --------------------------------------------------------
            # WELCOME VOICE
            # --------------------------------------------------------

            welcome_file = "welcome.mp3"

            try:
                if not os.path.exists(welcome_file):
                    await generate_speech(
                        "Hello everyone! I am Kriti. I am ready to talk with you.",
                        VOICE_MAPPING["en"],
                        welcome_file,
                    )

                await queue_audio(welcome_file)
                await wait_for_playback()

            except Exception as audio_error:
                print(
                    f"[Welcome Audio Error] {audio_error}"
                )

            # --------------------------------------------------------
            # START AUTOMATIC LISTENING
            # --------------------------------------------------------

            try:
                group_call.resume_recording()
            except Exception as recording_error:
                print(
                    f"[Recording Resume] {recording_error}"
                )

            voice_engine.resume()

            # --------------------------------------------------------
            # SUCCESS MESSAGE
            # --------------------------------------------------------

            await status_message.edit_text(
                "✅ <b>Successfully joined group VC.</b>\n\n"
                f"🎙 <b>Group:</b> {chat_title}\n"
                f"🆔 <code>{chat_id}</code>\n\n"
                "👤 <b>Session:</b> Connected\n"
                "🔊 <b>Voice Chat:</b> Connected\n"
                "🧠 <b>Gemini AI:</b> Active\n"
                "🎙 <b>Automatic listening:</b> Active\n\n"
                "Say <b>Hello Kriti</b>, <b>Hey Kriti</b>, "
                "<b>Hi Kriti</b> or simply <b>Kriti</b>, "
                "then speak normally.\n\n"
                "ℹ️ The bot itself does <b>not</b> need to be a "
                "member/admin of the target group."
            )

        except Exception as error:
            print(
                f"[Join VC Error] {error}"
            )

            try:
                voice_engine.pause()
            except Exception:
                pass

            try:
                if current_vc_chat_id is not None:
                    await group_call.stop()
            except Exception:
                pass

            current_vc_chat_id = None

            with playback_lock:
                playback_buffer.clear()

            error_text = str(error)

            if (
                "CHAT_ADMIN_REQUIRED" in error_text.upper()
                or "MANAGE_CALL" in error_text.upper()
            ):
                error_text += (
                    "\n\nTelegram is reporting that the SESSION_STRING "
                    "account needs the group's manage-call permission. "
                    "That permission cannot be bypassed by code."
                )

            if (
                "GROUPCALL_INVALID" in error_text.upper()
                or "GROUPCALL_FORBIDDEN" in error_text.upper()
                or "GROUPCALL_JOIN_MISSING" in error_text.upper()
            ):
                error_text += (
                    "\n\nMake sure the group already has an active "
                    "Voice Chat. This version does not create a new "
                    "Voice Chat, because Telegram requires manage-call "
                    "admin permission to create one."
                )

            if status_message:
                try:
                    await status_message.edit_text(
                        "❌ <b>Could not join the group Voice Chat.</b>\n\n"
                        f"<code>{error_text}</code>\n\n"
                        "👤 The configured SESSION_STRING account is used "
                        "for the group/VC connection.\n"
                        "👥 All users are allowed to use this command."
                    )
                except Exception:
                    await message.reply_text(
                        "❌ <b>Error joining VC:</b>\n\n"
                        f"<code>{error_text}</code>"
                    )
            else:
                await message.reply_text(
                    "❌ <b>Error joining VC:</b>\n\n"
                    f"<code>{error_text}</code>"
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
    """
    /leavevc is available to ALL users.

    It disconnects the single configured SESSION_STRING account from
    the currently connected Voice Chat.
    """

    global current_vc_chat_id

    async with vc_operation_lock:
        try:
            if current_vc_chat_id is None:
                await message.reply_text(
                    "ℹ️ <b>Kriti is not currently connected to a Voice Chat.</b>"
                )
                return

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
                "✅ <b>Successfully left bot VC.</b>\n\n"
                "👋 Kriti has disconnected from the Voice Chat."
            )

        except Exception as error:
            print(
                f"[Leave VC Error] {error}"
            )

            current_vc_chat_id = None

            with playback_lock:
                playback_buffer.clear()

            try:
                voice_engine.resume()
            except Exception:
                pass

            await message.reply_text(
                "❌ <b>Error leaving VC:</b>\n\n"
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
        "✅ BOT STARTED SUCCESSFULLY - waiting for /start"
    )

    print(
        "✅ Pyrogram modern -100 peer-id compatibility patch: ACTIVE"
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
