# Telegram Chat Summarizer

Scrapes messages from a Telegram group, summarizes them with Google Gemini (free), and posts the summary to a Telegram channel on a schedule.

```
#summary

1 - 3 Aug

Fraxlend Liquidation Process
 (https://t.me/source_group/443901)Partial liquidations prevent bad debt and smoothen liquidations.
56 🗯 39 👏

DeFi Governance Debate
 (https://t.me/source_group/445490)Users debate practicality of oracle-less protocols.
34 🗯 21 👏
```

---

## Setup guide

### Step 1 — Get your Telegram API credentials

1. Go to [my.telegram.org](https://my.telegram.org) and log in with your personal Telegram account
2. Click **API development tools**
3. Create an app (name and description don't matter)
4. Copy your **App api_id** (a number) and **App api_hash** (a string)

You'll need these in Step 4.

---

### Step 2 — Create a Telegram channel for output

1. In Telegram, create a new channel (can be private)
2. Note its username — e.g. `@my_summaries`

That's it. No bot needed. The app posts using your personal account.

---

### Step 3 — Get a free Gemini API key

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API key**
3. Copy the key

Free tier limits: 1,500 requests/day, 1M tokens/minute. More than enough for a daily summarizer.

To verify your key works and see which models are available on your account, run `list_models.py`:

```bash
export GOOGLE_API_KEY="your_gemini_api_key"
python3 list_models.py
```

Output looks like:
```
Model name                                         Supported methods
--------------------------------------------------------------------------------
models/gemini-2.0-flash                            ['generateContent', ...]
models/gemini-2.0-flash-lite                       ['generateContent', ...]
models/gemini-1.5-pro                              ['generateContent', ...]
```

The model name configured in `summarization.py` must exactly match one of these. See the [Troubleshooting](#troubleshooting) section if you get a 404 model not found error.

---

### Step 4 — Install dependencies and generate your session string

The app uses your personal Telegram account to both read from the source group and post to the output channel. You authenticate once locally and save the result as a session string.

```bash
pip install -r requirements.txt
```

Open `generate_session.py`, fill in your `API_ID` and `API_HASH` from Step 1:

```python
API_ID = 123456                      # ← your number
API_HASH = "your_api_hash_here"      # ← your string
```

Then run it:

```bash
python3 generate_session.py
```

Telegram will send an OTP to your phone — enter it when prompted, plus your 2-step verification password if you have one set. The session string prints to the terminal.

**Save the printed string.** You will never need to log in again — this string is reused on every run and on Railway.

---

### Step 5 — Configure the app

Edit `config.json`:

```json
{
  "log_level": "INFO",
  "telegram_api_id": 123456,
  "telegram_api_hash": "your_api_hash",
  "google_api_key": "your_gemini_api_key",
  "telegram_output_channels": ["@your_output_channel"],
  "chats_to_summarize": [
    {
      "id": "source_group_username",
      "lookback_period_seconds": 86400,
      "summarization_prompt_path": "prompts/example_summarization_prompt.txt",
      "backfill": false
    }
  ]
}
```

| Field | What to put |
|---|---|
| `telegram_api_id` | The number from Step 1 |
| `telegram_api_hash` | The string from Step 1 |
| `google_api_key` | The key from Step 3 |
| `telegram_output_channels` | Your channel username from Step 2, e.g. `["@my_summaries"]` |
| `id` | Username of the source group e.g. `"lobsters_chat"`, or numeric ID for private groups e.g. `-1001234567890` |
| `lookback_period_seconds` | How often to run AND how far back to look. `86400` = every 24 hrs |
| `backfill` | Set to `true` on first run to summarize all past messages, then `false` |

**Private group with no username?** Use `list_chats.py` to find its numeric ID.

Open `list_chats.py` and fill in your `API_ID` and `API_HASH`, then run:

```bash
export TELEGRAM_SESSION_STRING="your_session_string"
python3 list_chats.py
```

Output looks like:
```
ID                        Name
------------------------------------------------------------
-1001234567890            My Private Group
-1009876543210            Some Channel
```

Use the negative number as the `id` value — it never changes even if the invite link is revoked.

**Common intervals:**

| `lookback_period_seconds` | Interval |
|---|---|
| `43200` | Every 12 hours |
| `86400` | Every 24 hours |
| `172800` | Every 48 hours |

---

### Step 6 — Run locally

```bash
export TELEGRAM_SESSION_STRING="your_session_string_from_step_4"
python3 app.py config.json
```

You should see `Started!` in the logs. The first summary fires immediately and posts to your channel.

To test backfill (optional), set `"backfill": true` in `config.json` before running. It will chunk all historical messages into 24-hour windows and post a summary for each. Set it back to `false` once done.

---

### Step 7 — Deploy to Railway

Once it works locally, deploy to Railway so it runs 24/7.

**7a. Push the repo to GitHub**

Make sure secrets don't get committed:

```bash
echo "config.json" >> .gitignore
echo "*.session" >> .gitignore
git add .
git commit -m "initial commit"
git push
```

**7b. Create a Railway project**

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your repository
3. Railway detects the `Dockerfile` automatically

**7c. Set environment variables**

In Railway: open your service → **Variables** → add each one:

| Variable | Value |
|---|---|
| `TELEGRAM_API_ID` | From Step 1 |
| `TELEGRAM_API_HASH` | From Step 1 |
| `TELEGRAM_SESSION_STRING` | From Step 4 |
| `GOOGLE_API_KEY` | From Step 3 |
| `TELEGRAM_OUTPUT_CHANNEL` | e.g. `@my_summaries` |
| `SOURCE_CHAT_ID` | e.g. `lobsters_chat` |
| `LOOKBACK_PERIOD_SECONDS` | e.g. `86400` |
| `BACKFILL` | `true` for first deploy, `false` after |
| `LOG_LEVEL` | `INFO` |

**7d. Deploy**

Click **Deploy**. Watch the **Logs** tab — you should see `Started!` then the first summary posted to your channel.

If you set `BACKFILL=true` for the first deploy, wait until you see `Backfill complete` in the logs, then go to Variables, set `BACKFILL=false`, and Railway redeploys automatically.

---

## How it works

```
Your Telegram account (Telethon)
        │
        ├── reads messages from ──► Source Group
        │
        ├── sends text to ────────► Google Gemini (summarize)
        │
        └── posts summary to ─────► Output Channel
```

One account does everything — no bot, no extra credentials.

---

## Helper scripts

| Script | Purpose | Run |
|---|---|---|
| `generate_session.py` | Authenticate your Telegram account and print a reusable session string | `python3 generate_session.py` |
| `list_chats.py` | List all your groups and channels with their numeric IDs | `TELEGRAM_SESSION_STRING=x python3 list_chats.py` |
| `list_models.py` | List Gemini models available on your API key | `GOOGLE_API_KEY=x python3 list_models.py` |

All three are in `.gitignore` — they contain credentials and are for local use only.

---

## Troubleshooting

**`404 models/gemini-1.5-flash is not found`**
The model name in `summarization.py` doesn't match what's available on your API key. Run `list_models.py` to see what's available, then update the `self.model` value in `summarization.py` to match exactly — e.g. `"gemini-2.0-flash"`.

**`ValueError: Cannot find any entity`**
The `id` in `config.json` is a string but needs to be an integer for numeric IDs. Remove the quotes: `"id": -1001234567890` not `"id": "-1001234567890"`.

**`ModuleNotFoundError`**
Run `pip install -r requirements.txt` to install all dependencies.

---

## Customising the prompt

Edit `prompts/example_summarization_prompt.txt` to change the summary style or language instructions.

The file must contain `{text_to_summarize}` or the app will refuse to start. Available placeholders:

| Placeholder | Description |
|---|---|
| `{text_to_summarize}` | The scraped messages as JSON |
| `{chat_username}` | Source group username, used for building message links |
| `{date_range}` | e.g. `1 - 3 Aug` |
