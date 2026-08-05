# 🍵 The Everyday Matcha — Vendor Call Bot

Watches Facebook groups for bazaar and pop-up **"call for vendors"** posts,
scores them against what actually matters for a matcha booth, and pushes the
good ones into your Telegram group chat.

```
🔥 Strong match · 🍵 vendor call
📅 8-9 Aug (Sat-Sun) · ⭐️ Sunway Pyramid · 💰 from RM250 · 🥤 F&B welcome

  📢 CALL FOR VENDORS 📢
  Weekend Bazaar @ Sunway Pyramid
  Date: 8 & 9 Ogos 2026 (Sabtu & Ahad)
  Booth fee: RM250 for 2 days…

from KL Bazaar & Pop Up Vendors
Open post →
```

---

## One thing to know before you start

**Facebook Marketplace is the wrong place to look.** Marketplace is for
selling items — vendor calls essentially never appear there, and it is
heavily bot-protected. Bazaar organisers recruit in **Facebook Groups**, so
that is what this bot watches. You supply the groups; joining the right ones
matters more than anything in this code.

Search Facebook for groups like: *bazaar vendor Malaysia*, *pop up market
KL*, *bazaar Selangor*, *vendor booth Klang Valley*, *pasar malam vendor*.
Join 5–10 active ones, then add their URLs to `config.json`.

---

## Setup

Roughly 20 minutes, once.

### 1. Install

```bash
cd matcha-vendor-bot

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### 2. Add your groups

Open `config.json` and replace the placeholder with the groups you joined:

```json
"facebook_groups": [
  "https://www.facebook.com/groups/123456789",
  "https://www.facebook.com/groups/klbazaarvendors"
]
```

Open a group in your browser and copy the URL from the address bar — that is
all you need.

### 3. Create the Telegram bot

1. Open Telegram, search for **@BotFather**, send `/newbot`.
2. Give it a name (*Everyday Matcha Vendor Bot*) and a username ending in
   `bot`.
3. BotFather replies with a **token** like `8123456789:AAH...`. Copy it.
4. **Add the bot to your group chat** — group info → Add members → search
   your bot's username.
5. Send any message in that group (e.g. `hello`).
6. Open this URL in a browser, pasting your token in:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Find `"chat":{"id":-1001234567890` — that number, **including the minus
   sign**, is your chat id.

Now create your `.env`:

```bash
cp .env.example .env
```

Edit it:

```
TELEGRAM_BOT_TOKEN=8123456789:AAH...
TELEGRAM_CHAT_ID=-1001234567890
```

Test it:

```bash
python -m bot.run --test-telegram
```

You should get a message in the group. If it says *chat not found*, the bot
was not added to the group or the id is missing its minus sign.

> **Keep `.env` private.** It is gitignored. Anyone with that token can post
> as your bot. Never paste it into a chat window, screenshot, or commit.

### 4. Save your Facebook login

```bash
python -m bot.save_session
```

A browser window opens. Log in yourself — the bot never sees your password —
then press Enter in the terminal. This writes `fb_session.json`, a session
cookie the bot reuses so it does not log in on every run.

Re-run this whenever the bot reports the session expired (typically every few
weeks, or right after you change your Facebook password).

### 5. Try it without sending anything

```bash
python -m bot.run --dry-run
```

This scrapes, scores, and prints what it *would* send. Run it a few times
over a couple of days and check the matches look right before scheduling it.

### 6. Schedule it

| Your laptop | Setup guide |
|---|---|
| macOS | `deploy/macos-launchd.plist` |
| Linux | `deploy/linux-systemd.md` |
| Windows | `deploy/windows-task.md` |

All three are configured for **every 90 minutes** and catch up on runs missed
while the laptop was closed.

> Since this runs on your laptop, the bot only checks when the machine is
> awake. Closing it overnight means a gap — usually fine, since vendor calls
> stay open for days, but if you start missing things, a small always-on box
> (Raspberry Pi, cheap VPS) is the fix.

---

## How it decides what to send

Two stages. **Gates** are pass/fail; **signals** add up to a score.

### Gates — fail any of these and the post is dropped

| Gate | Why |
|---|---|
| Must contain a vendor/bazaar keyword | Otherwise it is not a booth post |
| Must not be someone *hunting* for a booth | *"Looking for a booth this weekend"* is another vendor, not an organiser |
| Must not explicitly exclude F&B | *"Preloved only, no F&B"* is dead on arrival for matcha |
| Event must not already be over | Thank-you posts and recaps |

### Signals — these produce the score

| Signal | Points |
|---|---|
| Vendor keywords | +2 each, max +6 |
| Organiser call to action (*"call for vendors"*, *"vendor registration"*, *"borang"*) | +5 |
| Priority venue (Sunway Pyramid, Mid Valley, Publika…) | +5 |
| Known venue / target area | +3 / +2 |
| Weekend date | +4 |
| F&B or drinks welcome | +3 |
| Free booth | +3 |
| Booth fee within budget | +2 (over budget: −3) |
| Mentions drinks or dessert | +1 |

Score maps to a tier so you can tell at a glance how hard to look:

- **17+ → 🔥 Strong match**
- **12–16 → ✅ Good match**
- **8–11 → 👀 Worth a look**
- **below 8 → not sent**

### Test the scoring on any post

Paste a real post and see exactly why it scored what it did:

```bash
python -m bot.run --score "CALL FOR VENDORS! Bazaar at Publika 22-23 Ogos, booth RM180, F&B welcome"
```

```
MATCH — score 25 (hot)
  +6 vendor keywords (3)
  +5 organiser call ('call for vendor')
  +4 weekend date
  +5 priority venue (Publika)
  +3 F&B / drinks welcome
  +2 booth fee RM180 within budget
```

This is the fastest way to tune your filters: find a post the bot got wrong,
run it through `--score`, and adjust the setting responsible.

---

## Tuning

Everything lives in `config.json`.

| Setting | Default | What it does |
|---|---|---|
| `min_score` | `8` | Lower → more alerts, more noise. Raise to `12` if it is too chatty. |
| `require_weekend` | `false` | Set `true` to send **only** weekend events. Off by default so a Friday-evening night market still reaches you — weekends are tagged 📅 either way. |
| `require_location` | `false` | Set `true` to drop anything with no recognised Klang Valley venue or area. Costs you posts that name a venue the bot has not heard of. |
| `max_booth_fee` | `400` | Fees above this lose points. |
| `drop_over_budget` | `false` | Set `true` to drop over-budget posts entirely rather than penalise them. |
| `priority_venues` | KL/Selangor malls | Your ⭐️ list. |
| `extra_venues` / `extra_areas` | `[]` | Add venues the bot does not know, or expand outside the Klang Valley — e.g. `"extra_venues": ["Gurney Plaza", "Queensbay Mall"]`. |
| `max_alerts_per_run` | `8` | Stops a first run against a busy group from dumping 40 messages into the chat. |
| `posts_per_group` | `25` | How far back each run reads. |

**You picked weekend-only when we scoped this.** It ships as a *tag* rather
than a hard filter because requiring both a weekend date *and* vendor
keywords drops any post where the organiser writes the date in a format the
parser misses — a silent miss you would never know about. Flip
`require_weekend` to `true` any time if the weekday posts annoy you.

---

## Everyday use

```bash
python -m bot.run                 # one normal run
python -m bot.run --dry-run       # scrape + score, print instead of send
python -m bot.run --score "..."   # score one post, explain the result
python -m bot.run --stats         # how many posts seen / alerts sent
python -m bot.run --verbose       # debug output, including why posts were skipped
tail -f data/bot.log              # what the scheduled runs have been doing
```

Run the tests after changing any filter logic:

```bash
python -m unittest discover -s tests -t .
```

---

## Troubleshooting

**"No saved Facebook session"** — run `python -m bot.save_session`.

**"Facebook redirected to login/checkpoint"** — the session expired or
Facebook flagged it. Log in normally in your own browser first, clear any
security prompt, then re-run `save_session`.

**"No post elements found"** — Facebook changed its markup. Open the group in
your browser, right-click a post → Inspect, and update `POST_SELECTORS` at
the top of `bot/facebook.py`. This is the one part of the bot that will break
periodically; it is unavoidable when scraping Facebook.

**Nothing is matching** — run with `--verbose` and read the skip reasons. The
usual cause is that the groups do not post many real vendor calls; the second
is `min_score` being too high.

**Too many irrelevant alerts** — raise `min_score` to 12, or set
`require_location` to `true`.

**Same post alerting twice** — happens when Facebook did not render a
permalink and the post text changed between runs (an edit, or a truncated
"See more"). Rare; harmless.

---

## Caveats, honestly

- **Facebook's terms.** Automating access with a personal account is against
  Facebook's ToS. Worst realistic case is a temporary checkpoint on the
  account. Keeping the interval at 90 minutes and the scroll depth modest is
  what keeps this looking like a person, not a crawler — do not lower it.
  Consider using a secondary account that is a member of the groups.
- **Scraping is brittle by nature.** Expect to update the selector once or
  twice a year.
- **Groups over code.** The bot can only find what gets posted in the groups
  you joined. Adding two more active groups will do more for your booth
  pipeline than any filter tweak.
- **Not everything gets caught.** Organisers who post only a poster image
  with no caption text are invisible to this bot — there is no text to read.

---

## Project layout

```
matcha-vendor-bot/
├── bot/
│   ├── run.py           # entry point + CLI
│   ├── config.py        # config.json + .env loading and validation
│   ├── facebook.py      # Playwright scraping
│   ├── matching.py      # gates, signals, scoring
│   ├── dates.py         # EN/MS date + weekend parsing
│   ├── venues.py        # Klang Valley venue and area vocabulary
│   ├── store.py         # SQLite dedup
│   ├── notifier.py      # Telegram delivery and message formatting
│   └── save_session.py  # one-time Facebook login
├── deploy/              # macOS / Linux / Windows schedulers
├── tests/               # 87 tests, no network needed
├── config.json          # your settings (safe to commit)
└── .env                 # your secrets (never commit)
```
