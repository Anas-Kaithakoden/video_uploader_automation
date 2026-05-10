"""
telegram_handler.py — Telegram bot with full conversation flow.

Flow:
  1. Video received
     - Has caption note → run pipeline immediately
     - No caption → 3-choice menu (auto / hint / full caption)
  2. Caption review loop (Yes / Edit)
  3. Platform selection (multi-select checkboxes → Upload button)
  4. Run scripts sequentially and report results
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import (
    ALLOWED_CHAT_ID,
    DOWNLOADS_DIR,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    TELEGRAM_BOT_TOKEN,
)
from logger import get_logger
from pipeline import run_pipeline
from storage.utils import _load as load_jobs

log = get_logger(__name__)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ── Conversation states ────────────────────────────────────────────────────────
CHOOSE_MODE        = 1
WAIT_SHORT_NOTE    = 2
WAIT_FULL_CAPTION  = 3
CONFIRM_CAPTION    = 4
WAIT_EDIT          = 5
SELECT_PLATFORMS   = 6   # user toggles platform checkboxes

# ── context.user_data keys ─────────────────────────────────────────────────────
_VIDEO_PATH       = "video_path"
_VIDEO_ID         = "video_id"
_CURRENT_CAPTION  = "current_caption"
_TITLE            = "title"
_TWITTER_TEXT     = "twitter_text"
_SELECTED         = "selected_platforms"   # set of selected platform names

ALL_PLATFORMS = ["youtube", "instagram", "twitter", "reddit"]
PLATFORM_LABELS = {
    "youtube":   "▶️ YouTube",
    "instagram": "📸 Instagram",
    "twitter":   "🐦 Twitter / X",
    "reddit":    "👽 Reddit",
}


# ── Auth ────────────────────────────────────────────────────────────────────────

def _is_authorized(update: Update) -> bool:
    if ALLOWED_CHAT_ID == 0:
        log.warning("ALLOWED_CHAT_ID not set — bot is open to everyone!")
        return True
    return update.effective_chat.id == ALLOWED_CHAT_ID


# ── Platform selection keyboard ────────────────────────────────────────────────

def _platform_keyboard(selected: set) -> InlineKeyboardMarkup:
    """Build a keyboard with toggleable platform buttons + an Upload button."""
    rows = []
    for p in ALL_PLATFORMS:
        label = PLATFORM_LABELS[p]
        tick  = "✅ " if p in selected else "◻️ "
        rows.append([InlineKeyboardButton(tick + label, callback_data=f"toggle_{p}")])

    # Only show Upload if at least one platform is selected
    if selected:
        rows.append([InlineKeyboardButton("🚀  Upload now", callback_data="do_upload")])
    else:
        rows.append([InlineKeyboardButton("← Select at least one platform", callback_data="noop")])

    return InlineKeyboardMarkup(rows)


# ── Caption helpers ────────────────────────────────────────────────────────────

async def _ask_confirm(update: Update, caption: str) -> None:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅  Looks good!", callback_data="caption_yes"),
            InlineKeyboardButton("✏️  Edit",        callback_data="caption_edit"),
        ]
    ])
    await update.effective_message.reply_text(
        f"📋 Caption:\n\n{caption}\n\nIs this good to go?",
        reply_markup=keyboard,
    )


def _refine_caption(current_caption: str, instructions: str) -> str:
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": (
                        "You are an Islamic social media content editor. "
                        "Apply ONLY the requested changes to the caption. "
                        "Keep Islamic tone and hashtags unless told otherwise. "
                        "Return ONLY the updated caption text — nothing else."
                    )},
                    {"role": "user", "content": (
                        f"Current caption:\n{current_caption}\n\n"
                        f"Changes requested:\n{instructions}\n\n"
                        "Return the updated caption."
                    )},
                ],
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 1024},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
    except Exception as exc:
        log.error(f"LLM refinement failed: {exc}")
        return current_caption


# ── Download helper ─────────────────────────────────────────────────────────────

async def _download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.video or update.message.document
    if not file_obj:
        await update.message.reply_text("Could not read the file. Please send a video.")
        return None

    file_name  = getattr(file_obj, "file_name", None) or f"{file_obj.file_unique_id}.mp4"
    video_path = os.path.join(DOWNLOADS_DIR, file_name)
    video_id   = os.path.splitext(file_name)[0]

    await update.message.reply_text(f"Downloading {file_name}...")

    try:
        tg_file = await context.bot.get_file(file_obj.file_id)
        await tg_file.download_to_drive(video_path)
        log.info(f"Downloaded: {video_path}")
        return video_path, video_id
    except Exception as exc:
        await update.message.reply_text(f"Download failed: {exc}")
        return None


# ── Pipeline → caption confirm ─────────────────────────────────────────────────

async def _run_pipeline_and_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    video_path: str, video_id: str, user_note: str = "",
) -> int:
    msg = update.effective_message
    await msg.reply_text("Processing...\n› Transcribing\n› Cleaning\n› Generating caption")

    try:
        result = run_pipeline(video_path, video_id=video_id, user_note=user_note)
    except Exception as exc:
        await msg.reply_text(f"Pipeline error: {exc}")
        return ConversationHandler.END

    if not result["success"]:
        await msg.reply_text(f"Failed: {result['error']}")
        return ConversationHandler.END

    await msg.reply_text(f"📝 Cleaned Subtitle:\n\n{result['english_cleaned']}")

    # Store everything needed for later steps
    context.user_data[_CURRENT_CAPTION] = result["caption"]
    context.user_data[_TITLE]           = result["title"]
    context.user_data[_TWITTER_TEXT]    = result["twitter_text"]
    context.user_data[_VIDEO_PATH]      = video_path

    await _ask_confirm(update, result["caption"])
    return CONFIRM_CAPTION


# ── Commands ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "🕌 Islamic Video Uploader Bot\n\n"
        "Send me a video. I'll transcribe it, generate a caption, let you review it, "
        "then upload to your chosen platforms.\n\n"
        "/status — recent jobs\n"
        "/cancel — cancel current operation"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    jobs = load_jobs()
    if not jobs:
        await update.message.reply_text("No jobs found yet.")
        return

    sorted_jobs = sorted(
        jobs.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True
    )[:10]

    lines = ["📋 Recent Jobs:\n"]
    for jid, job in sorted_jobs:
        emoji = {"processing": "⏳", "completed": "✅", "failed": "❌"}.get(job["status"], "❓")
        try:
            dt = datetime.fromisoformat(job.get("updated_at", "")).strftime("%d %b %Y  %H:%M")
        except Exception:
            dt = job.get("updated_at", "")[:16]
        title  = job.get("title") or "(no title)"
        method = job.get("transcription_method") or "pending"
        lines.append(f"{emoji} {jid} | {dt}\n   📌 {title}\n   🔧 {method}\n")

    await update.message.reply_text("\n".join(lines))


# ── Conversation entry ──────────────────────────────────────────────────────────

async def video_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_authorized(update):
        return ConversationHandler.END

    user_note  = (update.message.caption or "").strip()
    downloaded = await _download_video(update, context)
    if not downloaded:
        return ConversationHandler.END

    video_path, video_id = downloaded

    if user_note:
        return await _run_pipeline_and_confirm(update, context, video_path, video_id, user_note=user_note)

    context.user_data[_VIDEO_PATH] = video_path
    context.user_data[_VIDEO_ID]   = video_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣  Auto — AI decides the caption",        callback_data="mode_auto")],
        [InlineKeyboardButton("2️⃣  Give a hint — I'll describe briefly",  callback_data="mode_hint")],
        [InlineKeyboardButton("3️⃣  Full caption — I'll write it myself",  callback_data="mode_full")],
    ])
    await update.message.reply_text("How do you want to handle the caption?", reply_markup=keyboard)
    return CHOOSE_MODE


# ── Mode choice ─────────────────────────────────────────────────────────────────

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice     = query.data
    video_path = context.user_data.get(_VIDEO_PATH, "")
    video_id   = context.user_data.get(_VIDEO_ID, "")

    if choice == "mode_auto":
        await query.edit_message_text("1️⃣ Auto mode — running now...")
        return await _run_pipeline_and_confirm(update, context, video_path, video_id)

    elif choice == "mode_hint":
        await query.edit_message_text(
            "2️⃣ Hint mode\n\nSend me a short note about this video.\n"
            "Example: Sheikh Suleiman, story about a smile"
        )
        return WAIT_SHORT_NOTE

    elif choice == "mode_full":
        await query.edit_message_text(
            "3️⃣ Full caption mode\n\nSend me the complete caption text.\n"
            "I'll confirm it with you before uploading."
        )
        return WAIT_FULL_CAPTION

    return ConversationHandler.END


async def received_short_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_note  = update.message.text.strip()
    video_path = context.user_data.get(_VIDEO_PATH, "")
    video_id   = context.user_data.get(_VIDEO_ID, "")
    await update.message.reply_text(f"Got it: {user_note}")
    return await _run_pipeline_and_confirm(update, context, video_path, video_id, user_note=user_note)


async def received_full_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_caption = update.message.text.strip()

    if len(full_caption) > 280:
        await update.message.reply_text(
            f"Caption is {len(full_caption)} characters — must be 280 or less.\n"
            f"Please shorten it by {len(full_caption) - 280} characters and send again."
        )
        return WAIT_FULL_CAPTION   # stay in same state, let user try again

    lines = full_caption.splitlines()
    context.user_data[_CURRENT_CAPTION] = full_caption
    context.user_data[_TITLE]           = lines[0].lstrip("✨ ").strip() if lines else "Islamic Video"
    context.user_data[_TWITTER_TEXT]    = full_caption
    await _ask_confirm(update, full_caption)
    return CONFIRM_CAPTION


# ── Caption confirm loop ────────────────────────────────────────────────────────

async def caption_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Caption confirmed!")

    final_caption = context.user_data.get(_CURRENT_CAPTION, "")
    await update.effective_message.reply_text(final_caption)

    # Init platform selection with nothing selected
    context.user_data[_SELECTED] = set()

    await update.effective_message.reply_text(
        "Select platforms to upload to:",
        reply_markup=_platform_keyboard(set())
    )
    return SELECT_PLATFORMS


async def caption_edit_requested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ What should I change?\n\n"
        "Example: make the title shorter, add more Arabic hashtags"
    )
    return WAIT_EDIT


async def received_edit_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    instructions    = update.message.text.strip()
    current_caption = context.user_data.get(_CURRENT_CAPTION, "")
    await update.message.reply_text("Refining caption...")
    refined = _refine_caption(current_caption, instructions)
    context.user_data[_CURRENT_CAPTION] = refined
    await _ask_confirm(update, refined)
    return CONFIRM_CAPTION


# ── Platform selection ──────────────────────────────────────────────────────────

async def platform_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    selected = context.user_data.setdefault(_SELECTED, set())
    platform = query.data.replace("toggle_", "")

    # Toggle
    if platform in selected:
        selected.discard(platform)
    else:
        selected.add(platform)

    # Update the keyboard in-place
    await query.edit_message_reply_markup(reply_markup=_platform_keyboard(selected))
    return SELECT_PLATFORMS


async def do_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    selected     = context.user_data.get(_SELECTED, set())
    video_path   = context.user_data.get(_VIDEO_PATH, "")
    caption      = context.user_data.get(_CURRENT_CAPTION, "")
    title        = context.user_data.get(_TITLE, "Islamic Video")
    twitter_text = context.user_data.get(_TWITTER_TEXT, "")

    if not selected:
        await query.answer("Select at least one platform first.", show_alert=True)
        return SELECT_PLATFORMS

    platform_list = sorted(selected, key=lambda p: ALL_PLATFORMS.index(p))
    await query.edit_message_text(
        f"🚀 Uploading to: {', '.join(PLATFORM_LABELS[p] for p in platform_list)}\n\n"
        "Chrome will open for each platform. Don't touch it while it works."
    )

    # Run uploads
    from scripts_auto.runner import run_platforms
    results = await run_platforms(
        platforms    = platform_list,
        video_path   = os.path.abspath(video_path),
        title        = title,
        caption      = caption,
        twitter_text = twitter_text,
    )

    # Report results
    lines = ["📊 Upload Results:\n"]
    for platform, res in results.items():
        emoji = "✅" if res["success"] else "❌"
        label = PLATFORM_LABELS.get(platform, platform)
        error = f"\n   ↳ {res['error']}" if res.get("error") else ""
        lines.append(f"{emoji} {label}{error}")

    await update.effective_message.reply_text("\n".join(lines))
    context.user_data.clear()
    return ConversationHandler.END


async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the disabled 'select at least one' button."""
    await update.callback_query.answer()
    return SELECT_PLATFORMS


# ── Cancel ──────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── App builder ─────────────────────────────────────────────────────────────────

def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.VIDEO | filters.Document.VIDEO | filters.Document.ALL,
                video_received
            )
        ],
        states={
            CHOOSE_MODE: [
                CallbackQueryHandler(mode_chosen, pattern="^mode_")
            ],
            WAIT_SHORT_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_short_note)
            ],
            WAIT_FULL_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_full_caption)
            ],
            CONFIRM_CAPTION: [
                CallbackQueryHandler(caption_confirmed,      pattern="^caption_yes$"),
                CallbackQueryHandler(caption_edit_requested, pattern="^caption_edit$"),
            ],
            WAIT_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_instructions)
            ],
            SELECT_PLATFORMS: [
                CallbackQueryHandler(platform_toggle, pattern="^toggle_"),
                CallbackQueryHandler(do_upload,       pattern="^do_upload$"),
                CallbackQueryHandler(noop,            pattern="^noop$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(conv)
    return app


def run_bot() -> None:
    log.info("Starting Telegram bot (polling mode)...")
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)