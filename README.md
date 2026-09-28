# Doxa Family Church Agents

Small helpers that take routine church work off people's hands. Each agent runs free on GitHub Actions: there is no server to rent and nothing to install on a computer.

| Agent | What it does | Workflow |
|---|---|---|
| **Church Announcer** | The secretary sends the week's announcements to a Telegram group. The bot replies with a polished script and an MP3 that the media team plays during service. | `Church Announcer` |

More agents will be added to this repo as new folders next to `announcer/`.

---

# Church Announcer

## How it works

1. The secretary posts the announcements in the church's Telegram announcements group.
2. GitHub checks the group on a schedule (see [When it checks](#when-it-checks)).
3. Google's Gemini AI turns the text into a warm spoken script. It keeps every name, date, time, amount and venue exactly as written.
4. A Nigerian English voice reads the script into an MP3.
5. The bot replies in the group with the script and the MP3.

If the AI is unavailable, or it changes or drops a detail, the bot reads the secretary's original text instead and says so. If the main voice is down, a backup voice is used. If both voices fail, the bot says so in the group and still sends the script, so it never fails silently.

Cost: ₦0. Telegram, Gemini's free tier, the voices and GitHub Actions for a public repo are all free.

---

## One-time setup

You need a Telegram account, a Google account and a GitHub account. The whole setup takes about 20 minutes.

### 1. Create the bot (Telegram)
1. In Telegram, open a chat with **@BotFather** (it has a blue tick).
2. Send `/newbot`. Give it a name (for example *Doxa Announcer*) and a username ending in `bot` (for example `DoxaAnnouncerBot`).
3. BotFather replies with a **token**, a long code like `123456:ABC-DEF…`. Copy it and keep it private. Anyone with the token can control the bot.
4. Still in BotFather, send `/setprivacy`, choose your bot, then choose **Disable**. This lets the bot read ordinary messages in the group.

### 2. Put the bot in the group
1. Open the announcements group (the one with the secretary and the media team). Choose **Add members** and add the bot.
2. Send any message in the group, for example `hello`.

### 3. Find the group's ID
**Easiest:** on a computer with this repo, run `python -m announcer.find_chats`, paste the token when asked, and it prints the group's ID. It also tells you if privacy mode or a webhook is getting in the way.

**Or by hand:**
1. On a computer, open this address in a browser, replacing `<TOKEN>` with the bot's token:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
2. Look for `"chat":{"id":-100…`. The number, **including the minus sign**, is the group ID.
3. To let the secretary also message the bot privately, have them send it `/help` directly, refresh the page, and note their ID too (a positive number).

> If the group is ever upgraded (Telegram does this automatically when it gets large or when some settings change), its ID changes. When the bot suddenly stops answering, repeat this step.

### 4. Get a Gemini key (Google AI Studio)
1. Go to **aistudio.google.com**, sign in, and click **Get API key**, then **Create API key**. Copy it.
2. Find the name of the current **Flash** model. It is listed on the models page of the Gemini API documentation and looks like `gemini-…-flash`. Use whichever Flash model is current on the free tier.

### 5. Add the settings to GitHub
In this repository, go to **Settings → Secrets and variables → Actions**.

On the **Secrets** tab, click **New repository secret** for each of these:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The token from step 1 |
| `GEMINI_API_KEY` | The key from step 4 |
| `ALLOWED_CHAT_IDS` | The group ID from step 3. Separate more than one with commas, e.g. `-1001234567890,123456789` |

On the **Variables** tab, click **New repository variable** for each of these:

| Name | Value |
|---|---|
| `GEMINI_MODEL` | The Flash model name from step 4 |
| `CHURCH_NAME` *(optional)* | e.g. `Doxa Family Church`. If set, the greeting names the church. Leave it out for a general greeting. |
| `VOICE_FEMALE` *(optional)* | The voice `/voice female` uses (and the default). Default `en-NG-EzinneNeural`. |
| `VOICE_MALE` *(optional)* | The voice `/voice male` uses. Default `en-NG-AbeoNeural`. |
| `VOICE_RATE` *(optional)* | Reading speed. Default `-15%` (a little slower than normal). Use e.g. `-25%` for slower or `+0%` for normal. |

Anyone in the group can switch between the female and male voice with `/voice male` or `/voice female`. Other voice names to try: `en-US-AvaNeural`, `en-GB-SoniaNeural`, `en-KE-AsiliaNeural` (female); `en-US-AndrewNeural`, `en-GB-RyanNeural`, `en-ZA-LukeNeural` (male).

Messages from any chat that isn't in `ALLOWED_CHAT_IDS` are ignored.

### 6. Test it
1. Post a test announcement in the group, for example: *Choir rehearsal holds on Saturday at 4pm in the main auditorium. Harvest levy is ₦5,000 per family.*
2. In GitHub, open the **Actions** tab, click **Church Announcer** on the left, then click **Run workflow → Run workflow**.
3. Within about two minutes, the bot should reply in the group with the script and the MP3.

---

## Using it

| Send this | You get |
|---|---|
| The announcements, as a normal message | Script + MP3 |
| `/preview` followed by the announcements | Script only, no audio (useful for checking the wording) |
| `/voice male` or `/voice female` | Changes the voice for every MP3 from then on |
| `/help` | A one-line reminder |

**In the group, the bot ignores everyday chat.** It only acts on:
- a message of **6 words or more** that is not a reply to someone else,
- any message that **mentions the bot** (e.g. `@DoxaAnnouncerBot Service starts at 8am`),
- any **reply to the bot's own messages**.

So "Amen 🙏" or "Received, thanks" won't produce an MP3. To send a very short announcement, mention the bot.

**Made a mistake?** Edit the message in Telegram. On its next check, the bot replies with an *Updated script* and a new MP3.

## When it checks

Times are Nigerian time (WAT).

| When | How often |
|---|---|
| Friday and Saturday | Every 20 minutes |
| Sunday 06:00–09:00 | Continuously: replies arrive within seconds |
| Rest of Sunday | Every 20 minutes |
| Monday–Thursday | Twice a day (01:00 and 13:00) |

Aim to send the Sunday script by **07:00**. The MP3 will be in the group well before 07:15.

GitHub sometimes starts scheduled checks a few minutes late. If something is urgent, press **Run workflow** (step 6) to check immediately.

On Sunday morning the Actions list shows some grey "cancelled" runs. That's normal: they are extra checks that weren't needed because the bot was already listening.

## When something goes wrong

| What you see | What to do |
|---|---|
| No reply at all | Actions tab → open the latest **Church Announcer** run. Red means it failed, and the log says why (missing setting, wrong token, etc.). |
| "Missing required settings" in the log | A secret or variable from step 5 is missing or misspelled. |
| The bot stopped answering the group | The group ID may have changed. Repeat step 3 and update `ALLOWED_CHAT_IDS`. |
| "…this is your text as written" | The AI was down, or it tried to change a detail. The MP3 reads the original text, so it is still correct. |
| "(backup voice)" on the MP3 | The main voice service was down, so the offline backup voice was used. |
| An email from GitHub about a disabled workflow | Open the Actions tab and click **Enable workflow**. (The workflow re-enables itself monthly to prevent this, but act on the email if it ever arrives.) |

Privacy: announcement text is never stored. It travels only through Telegram, Gemini and the voice service. The run logs are public because the repo is public, so they record only counts, never message text, names or chat IDs.

## Handing it over to the media team

See [docs/handover-checklist.md](docs/handover-checklist.md).

---

## For developers

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

Run one polling pass locally (set the same environment variables as in step 5 first):

```bash
python -m announcer.main                          # one pass, then exit
python -m announcer.main --listen-until 08:00     # keep listening until 08:00 UTC
```

| File | Role |
|---|---|
| `announcer/main.py` | Poll → process → reply → confirm each update, then exit |
| `announcer/script.py` | Gemini rewrite, emoji/markdown clean-up, fact guard (every number and name must survive) |
| `announcer/numbers.py` | ₦ amounts and clock times → words, done in code rather than by the AI |
| `announcer/voice.py` | edge-tts, falling back to Piper |
| `announcer/telegram.py` | Bot API client. Errors never include the token |
| `announcer/config.py` | Environment settings |

Optional variables: `PIPER_VOICE_FEMALE` / `PIPER_VOICE_MALE` (the backup voices, default `en_GB-jenny_dioco-medium` / `en_GB-alan-medium`) and `MIN_GROUP_WORDS` (default 6).

The `/voice` choice lives in the bot's own Telegram short description, so the agent still needs no database.
