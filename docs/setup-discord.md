# Discord Bot Setup Guide

## Prerequisites

- A Discord account with "Manage Server" permission on the target server
- Access to the w7-ragKB admin dashboard
- Docker Compose environment running

## 1. Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g., "w7-ragKB")
3. Navigate to **Bot** → **Add Bot**
4. Under the bot section:
   - Copy the **Token** — save it securely
   - Enable **Message Content Intent** under Privileged Gateway Intents
   - Enable **Server Members Intent** if you want user info

## 2. Set Bot Permissions

Under **OAuth2** → **URL Generator**:

1. Select scopes: `bot`, `applications.commands`
2. Select bot permissions:
   - Send Messages
   - Read Message History
   - Embed Links
   - Attach Files
   - Use Slash Commands
   - Add Reactions
3. Copy the generated URL and open it to invite the bot to your server

## 3. Add Token to Environment

Add the bot token to your `.env` file:

```bash
DISCORD_BOT_TOKEN=your-discord-bot-token-here
```

Restart the slack-bot service:

```bash
docker compose restart slack-bot
```

## 4. Configure in Dashboard

1. Open the admin dashboard at `http://your-server:8080/admin`
2. Navigate to **Gateway** → **Channels** tab
3. Click **Add Channel** (or use the **Setup Wizard**)
4. Select **Discord** as the platform
5. Enter your bot token
6. Set rate limit (recommended: 45 messages/minute)
7. Enable the channel and save

## 5. Test the Connection

1. In the Channels table, click the **...** menu on your Discord channel
2. Select **Test Connection**
3. You should see a success message

In Discord:
1. Go to a channel where the bot has access
2. Mention the bot (`@w7-ragKB`) or use a configured trigger
3. The bot should respond with an AI-generated message

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot is offline | Check `DISCORD_BOT_TOKEN`, ensure intents are enabled |
| "Missing Permissions" | Re-invite with correct permissions using the OAuth URL |
| Bot doesn't respond to messages | Enable "Message Content Intent" in the Developer Portal |
| Embeds not showing | Ensure "Embed Links" permission is granted |
| Rate limited by Discord | Discord allows 50 requests/second. Reduce rate limit if needed |

## Discord-Specific Features

- **Max message length:** 2000 characters (4000 with Nitro)
- **Embeds:** Rich embed cards with colored borders, fields, thumbnails
- **Slash commands:** Register with Discord's interaction system
- **File uploads:** Up to 25MB (50MB with Nitro server boost)
- **Threads:** Supported for organized conversations
