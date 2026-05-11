# Telegram Bot Setup Guide

## Prerequisites

- A Telegram account
- Access to the w7-ragKB admin dashboard
- Docker Compose environment running

## 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g., "w7-ragKB Assistant")
   - Choose a username ending in `bot` (e.g., `w7ragkb_bot`)
3. BotFather will give you a **bot token** like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
4. Save this token securely

## 2. Configure Bot Settings (Optional)

With BotFather, you can also:
- `/setdescription` — set what users see before starting a chat
- `/setabouttext` — short bio text
- `/setuserpic` — bot profile photo
- `/setcommands` — add command hints (e.g., `/start`, `/help`)

## 3. Add Token to Environment

Add the bot token to your `.env` file:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

Restart the slack-bot service to pick up the new token:

```bash
docker compose restart slack-bot
```

## 4. Configure in Dashboard

1. Open the admin dashboard at `http://your-server:8080/admin`
2. Navigate to **Gateway** → **Channels** tab
3. Click **Add Channel** (or use the **Setup Wizard**)
4. Select **Telegram** as the platform
5. Enter your bot token
6. Set rate limit (recommended: 30 messages/minute for Telegram)
7. Enable the channel and save

## 5. Test the Connection

1. In the Channels table, click the **...** menu on your Telegram channel
2. Select **Test Connection**
3. You should see a success message

Alternatively, open Telegram:
1. Search for your bot by username
2. Press **Start**
3. Send a message — you should get a response from the AI agent

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot doesn't respond | Check `TELEGRAM_BOT_TOKEN` is set correctly, restart service |
| "Unauthorized" error | Token may be revoked — generate a new one from BotFather |
| Rate limiting | Telegram limits bots to ~30 messages/second. Reduce rate limit in settings |
| Messages delayed | Check queue depth in Gateway Metrics. High queue = system under load |
| Bot can't be found | Ensure the bot username is correct and publicly searchable |

## Telegram-Specific Features

- **Max message length:** 4096 characters
- **Inline keyboards:** Supported — the agent can send interactive button grids
- **Markdown:** Telegram uses its own MarkdownV2 format
- **File uploads:** Up to 50MB for documents, 20MB for photos
