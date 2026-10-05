import os

API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here")
SESSION_STRING = os.environ.get("SESSION_STRING", "your_pyrogram_string_session_here")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "your_gemini_api_key_here")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "your_groq_api_key_here")
