# Deploy with Claude Code (for non-programmers)

You do **not** need to know how to code to put this app online. Claude Code is an AI
assistant that runs on your computer, reads this project, and can do the technical
work while explaining each step in plain language. This page shows you how to let it
deploy the app for you.

## What you'll need

- A computer (macOS, Windows or Linux).
- A free **GitHub** account — <https://github.com> (stores the code).
- A **Railway** account — <https://railway.app> (runs the app; has a free trial).
- A **Claude** account for Claude Code — <https://www.claude.com/product/claude-code>.
- A way to pay the AI/scraping providers as you use them (a few dollars to start).

You'll collect a handful of "keys" along the way. A key is just a long password that
lets the app use a service (like OpenAI or Apify). Claude Code will tell you exactly
which website to open and where to click for each one — you don't need to know them
in advance.

## Step 1 — Install Claude Code

Follow the official installer: <https://www.claude.com/product/claude-code>.
When it's ready, you'll be able to open a project folder and chat with it.

## Step 2 — Get this project onto your computer

Easiest: on the project's GitHub page, click **Fork** (top-right) to copy it to your
own account, then **Code → Download ZIP** and unzip it — or let Claude Code clone it
for you in Step 3 by giving it the repository link.

## Step 3 — Open the project and paste this prompt

Open the project folder in Claude Code, then paste this message and send it:

```
You are my deployment assistant for this ВидеоРентген (VideoRentgen) project. I am not a programmer.
Guide me step by step to deploy it to production on Railway, in the language I write to you.

Rules:
- First read docs/SETUP_WITH_CLAUDE_CODE.md, docs/DEPLOY_RAILWAY.md and docs/GETTING_KEYS.md, then follow them.
- Do ONE step at a time and wait for me to confirm before the next.
- Whenever you need an API key, tell me exactly which website to open, where to click
  to get it, and what it looks like — then ask me to paste it. Never invent values.
- After I set environment variables, run `python scripts/check_env.py` with me to verify.
- Assume I know no commands: give me exact copy-paste commands and say where to run them.

Begin with a short overview of what we'll do and the rough monthly cost, then start step 1.
```

## What happens next

Claude Code will:

1. Explain the plan and the rough cost.
2. Walk you through creating the Railway project and adding the Postgres and Redis
   databases.
3. Ask you for one key at a time — telling you which site to open and where to find it.
4. Set everything up, run a check (`python scripts/check_env.py`) so you can see what's
   configured, deploy, and confirm the site is live.
5. Help you make yourself the admin and turn on any extra features you want (payments,
   Telegram, logins) later.

You can stop and resume any time — just reopen the folder and tell Claude Code where
you left off.

## A few safety rules

- **Keys are secret.** Paste them only where Claude Code tells you (your `.env` file or
  Railway's variables screen). Never post a key in a public chat, screenshot or issue.
- **You're using your own accounts.** The AI, scraping and hosting bills go to you via
  those providers — set spending limits in their dashboards if you're worried.
- **Make it yours.** Before showing the site to others, ask Claude Code to help you edit
  `frontend/src/region.ts` so your **own** brand name, company/legal details and support
  contact appear — not placeholder text.
- **Play fair.** Downloading from Instagram/TikTok/YouTube must follow their terms and
  your local laws. Use it responsibly.

That's it. The rest is a conversation — Claude Code handles the technical parts.
