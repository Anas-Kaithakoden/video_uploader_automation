# 🕌 Islamic Video Uploader Bot

A fully automated Python system that takes Islamic lecture/reminder videos via Telegram, extracts and cleans the speech, generates a social media caption using a local LLM, and uploads to multiple platforms — all from your phone.

---

## ✨ Features

- **Telegram bot** — send a video from your phone, get back a polished caption
- **Arabic speech-to-English** — Whisper transcribes and translates Arabic audio in one step
- **OCR fallback** — if audio fails, extracts burned-in English subtitles using Tesseract
- **LLM cleaning** — local Llama 3 (via Ollama) cleans and polishes the transcript
- **Caption generation** — LLM generates a ready-to-post caption (≤280 chars, 3–5 hashtags)
- **Caption review loop** — approve or edit the caption before anything is posted
- **Multi-platform upload** — YouTube, Instagram, Twitter/X, Reddit via Playwright browser automation
- **No cloud APIs** — everything runs locally, completely free
- **Access control** — bot only responds to your Telegram account

---

## 📁 Project Structure

```
islamic_uploader/
│
├── main.py                  # Entry point (bot or CLI mode)
├── config.py                # All settings loaded from .env
├── logger.py                # Rotating log to logs/pipeline.log
├── pipeline.py              # Orchestrates the 3-step pipeline
│
├── transcriber.py           # Step 1a: Whisper speech-to-English
├── ocr_fallback.py          # Step 1b: Tesseract OCR fallback
├── text_cleaner.py          # Step 2: LLM text cleaning
├── caption_generator.py     # Step 3: LLM caption generation
│
├── telegram_handler.py      # Telegram bot logic (ConversationHandler)
│
├── scripts_auto/            # Platform upload scripts (Playwright)
│   ├── youtube.py
│   ├── instagram.py
│   ├── twitter.py
│   ├── reddit.py
│   ├── runner.py            # Runs platforms sequentially in isolated loops
│   └── session_maker.py     # use to make sessions
│
├── storage/
│   ├── utils.py             # Job tracker (jobs.json)
│   └── jobs.json            # Auto-generated job history
│
├── downloads/               # Videos downloaded from Telegram
├── output/                  # Transcripts + captions saved per video
├── logs/                    # pipeline.log
├── sessions/                # Playwright browser sessions (login state)
│   ├── youtube_session/
│   ├── instagram_session/
│   ├── x_session/
│   └── reddit_session/
│
├── .env                     # Your secrets (never commit this)
├── .env.example             # Template for .env
└── requirements.txt
```

---

## 🔧 Requirements

### System
- Python 3.12
- [ffmpeg](https://ffmpeg.org/) — for OCR frame extraction
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — for subtitle fallback
- [Google Chrome](https://www.google.com/chrome/) — for browser automation
- [Ollama](https://ollama.com/) — to run Llama 3 locally

### Python packages
```
pip install -r requirements.txt
```

### Playwright browser
```
playwright install chrome
```

---

## ⚙️ Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd islamic_uploader
pip install -r requirements.txt
playwright install chrome
```

### 2. Install system tools

**Windows:**
- Download and install [ffmpeg](https://ffmpeg.org/download.html) — add to PATH
- Download and install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

**Linux/Mac:**
```bash
sudo apt install ffmpeg tesseract-ocr
```

### 3. Install and start Ollama

```bash
# Install from https://ollama.com
ollama pull llama3
ollama serve
```

### 4. Configure `.env`

Copy `.env.example` to `.env` and fill in your values:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here    # from @BotFather
ALLOWED_CHAT_ID=123456789                 # from @userinfobot

# Whisper (tiny/base/small/medium/large — small minimum for Arabic)
WHISPER_MODEL=small

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT=120

# Chrome profile (for YouTube — if using Profile 2)
CHROME_USER_DATA=C:/Users/YOUR_NAME/AppData/Local/Google/Chrome/User Data
CHROME_PROFILE=Profile 2

# OCR fallback
OCR_FRAME_INTERVAL=2
OCR_LANG=eng
OCR_CROP_BOTTOM_PERCENT=0.20
```

### 5. Set up platform sessions

Each platform uses its own persistent Chrome session stored in `sessions/`. On first run, the browser opens and you log in manually — the session is saved for all future runs.

Run each platform once manually to log in:

```bash
# The first time you run the bot and trigger an upload,
# Chrome will open. Log in to the platform, then it saves the session.
# You only do this once per platform.
```

Sessions are stored at:
```
sessions/youtube_session/
sessions/instagram_session/
sessions/x_session/
sessions/reddit_session/
```

---

## 🚀 Running

### Bot mode (normal use)
```bash
python main.py bot
# or just:
python main.py
```

### CLI mode (test without Telegram)
```bash
python main.py cli path/to/video.mp4
```

---

## 📱 How to Use (Telegram)

### Sending a video

1. Open your Telegram bot
2. Send a video file

**Option A — with a note attached:**
Add a caption to the video before sending (the text field below the video in Telegram). Example:
```
Sheikh Suleiman Al-Rehaili, touching story about the power of a smile
```
The bot will use your note as context when generating the caption.

**Option B — without a note:**
Send the video with no caption. The bot will ask:

```
How do you want to handle the caption?

[ 1️⃣ Auto — AI decides the caption        ]
[ 2️⃣ Give a hint — I'll describe briefly  ]
[ 3️⃣ Full caption — I'll write it myself  ]
```

| Choice | What happens |
|--------|-------------|
| **Auto** | Whisper transcribes → LLM generates caption |
| **Hint** | You type a short note → LLM uses it as context |
| **Full caption** | You write the whole caption (≤280 chars) — no AI processing |

### Reviewing the caption

After processing, the bot sends:
1. 📝 The cleaned English subtitle/transcript
2. 📋 The generated caption with a confirmation prompt:

```
[ ✅ Looks good! ]  [ ✏️ Edit ]
```

- **Looks good** → caption confirmed, move to platform selection
- **Edit** → type your change instructions (e.g. *"make the title shorter, remove Arabic hashtags"*) → LLM refines → shows again

### Selecting platforms

```
Select platforms to upload to:

[ ◻️ ▶️ YouTube        ]
[ ◻️ 📸 Instagram      ]
[ ◻️ 🐦 Twitter / X   ]
[ ◻️ 👽 Reddit         ]

[ 🚀 Upload now ]   ← appears after selecting at least one
```

Tap any platform to toggle it on/off. Tap **Upload now** when ready. Chrome opens for each platform in sequence and uploads automatically.

### Commands
| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and instructions |
| `/status` | Show last 10 processed videos with title, date, method |
| `/cancel` | Cancel current operation |

---

## 🔁 Pipeline

```
Video file
    │
    ▼
[ Step 1 ] Whisper  ──── Arabic audio ──→ English text
               │
               └── failed? ──→ Tesseract OCR (burned-in English subtitles)
    │
    ▼
[ Step 2 ] Llama 3 cleans the English text
           (removes duplicates, fixes grammar, preserves Islamic tone)
    │
    ▼
[ Step 3 ] Llama 3 generates caption
           (title + description + hashtags, ≤280 chars total)
    │
    ▼
[ Review ] You approve or edit the caption via Telegram buttons
    │
    ▼
[ Upload ] Playwright opens Chrome for each selected platform
           Each runs in an isolated event loop (no interference)
```

---

## 📋 Caption Format

The LLM generates one universal caption used across all platforms:

```
✨ A Smile That Changed Their Entire Life

A touching story about how a simple act of kindness led an entire family to Islam. A beautiful reminder that dawah doesn't need words.

#Islam #Dawah #Quran #IslamicReminder #SubhanAllah
```

| Platform | What it receives |
|----------|-----------------|
| **Instagram** | Full caption as-is |
| **Twitter/X** | Full caption as-is (≤280 chars guaranteed) |
| **YouTube** | Title extracted from line 1, rest as description |
| **Reddit** | Title extracted from line 1, rest as post body |

---

## 🗂️ Job History

Every processed video is logged in `storage/jobs.json`:

```json
{
  "8a599de7": {
    "video_id": "video1",
    "title": "A Smile That Changed Their Entire Life",
    "status": "completed",
    "transcription_method": "whisper",
    "created_at": "2026-05-05T01:14:02+00:00",
    "updated_at": "2026-05-05T01:14:54+00:00",
    "platforms_completed": [],
    "error": ""
  }
}
```

View via `/status` in Telegram or open the file directly.

---

## ⚠️ Notes

- **Close Chrome** before starting the bot — Playwright can't open a Chrome profile that's already in use
- **Ollama must be running** — start it with `ollama serve` before running the bot
- **Whisper model** — `small` is the minimum for Arabic. Use `medium` for better accuracy (needs ~5GB RAM)
- **Sessions** — if a platform logs you out, just delete its session folder and re-run to log in again
- **Reddit flairs** — hardcoded for `r/TrueDeen` and `r/islam` in `scripts_auto/reddit.py`. Edit `SUBREDDITS` list to change
- **Headless mode** — keep `headless=False`. Instagram and Twitter have aggressive bot detection

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `TELEGRAM_BOT_TOKEN not set` | Check your `.env` file |
| `Cannot connect to Ollama` | Run `ollama serve` in a separate terminal |
| `Whisper model loading slow` | Normal on first run — model is downloaded once |
| Chrome opens but is already logged out | Delete the session folder and re-run |
| Upload fails with timeout | The platform UI may have changed — check manually |
| `UnicodeEncodeError` in console | Make sure you're on Python 3.12, the logger handles this automatically |

---

## 📦 Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.12 | Core language |
| [python-telegram-bot](https://python-telegram-bot.org/) 20.7 | Telegram bot |
| [OpenAI Whisper](https://github.com/openai/whisper) | Arabic speech → English text |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Subtitle extraction fallback |
| [Ollama](https://ollama.com/) + Llama 3 | Local LLM (text cleaning + captions) |
| [Playwright](https://playwright.dev/python/) | Browser automation for uploads |
| ffmpeg | Video frame extraction (OCR fallback) |
