# Configuration Guide

LucidMind uses environment variables for all configuration. Copy `.env.example` to `.env` and fill in the values you need.

```bash
cp .env.example .env
```

## LLM Providers

At least one LLM provider is required. LucidMind supports automatic failover — configure multiple providers for resilience.

| Variable | Provider | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek | Default primary model (`deepseek-chat`) |
| `MINIMAX_API_KEY` | MiniMax | MiniMax-M2.5 via Anthropic-compatible API |
| `OPENAI_API_KEY` | OpenAI | GPT-4o / GPT-4o-mini |
| `ANTHROPIC_API_KEY` | Anthropic | Claude 3.5 Sonnet |
| `GEMINI_API_KEY` | Google Gemini | Gemini Pro |
| `GROQ_API_KEY` | Groq | Fast inference (Llama, Mixtral) |
| `MOONSHOT_API_KEY` | Moonshot | Kimi |
| `XAI_API_KEY` | xAI | Grok |
| `MISTRAL_API_KEY` | Mistral | Mistral Large |
| `ANTIGRAVITY_API_KEY` | Local proxy | Custom endpoint at `127.0.0.1:8045` |

### Model Switching

Switch the active model at runtime via the API:

```bash
curl -X POST http://localhost:8765/api/provider/switch \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai"}'
```

Or configure in `adapters/llm/model_catalog.json`.

### Local Models (Ollama)

```env
OLLAMA_URL=http://localhost:11434
```

LucidMind auto-detects local Ollama models at startup.

## Embedding

For vector-based memory search (optional but recommended):

```env
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_BASE_URL=https://api.openai.com/v1
```

Without embedding, memory search falls back to FTS5 full-text search only.

## Channels

### Telegram

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USERS=user_id1,user_id2   # optional whitelist
```

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Copy the token to `.env`
3. Restart LucidMind — the bot starts automatically

### Discord

```env
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_ALLOWED_CHANNELS=channel_id1,channel_id2   # optional
```

1. Create an application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Add a Bot, enable **Message Content Intent**
3. Invite to your server with `bot` + `applications.commands` scopes
4. Copy the token to `.env`

Requires: `pip install discord.py`

### Feishu (Lark)

```env
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

### WeCom (Enterprise WeChat)

```env
WECOM_CORP_ID=your_corp_id
WECOM_AGENT_ID=your_agent_id
WECOM_SECRET=your_secret
WECOM_TOKEN=your_callback_token
WECOM_ENCODING_AES_KEY=your_aes_key
```

### WeChat (via GeweChat)

```env
GEWECHAT_BASE_URL=http://localhost:2531
GEWECHAT_CALLBACK_URL=http://your-server:8765/api/channel/wechat/callback
GEWECHAT_TOKEN=your_token
WECHAT_ALLOWED_WXIDS=wxid1,wxid2   # optional whitelist
```

## MCP (Model Context Protocol)

```env
MCP_SERVERS=server1_url,server2_url
```

MCP servers are auto-discovered at startup and their tools become available to the Brain.

## Network

```env
HTTP_PROXY=http://proxy:port
HTTPS_PROXY=http://proxy:port
SEARXNG_URL=http://localhost:8080   # for web search tool
```

## Security

```env
JWT_SECRET=your_random_secret       # for API authentication
```

## Email Notifications

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASS=your_password
```

## Vision

```env
VISION_API_URL=http://localhost:11434/api/generate
VISION_MODEL=llava
```

## Runtime Configuration

Most settings can be changed at runtime via the web UI or API without restarting:

- **Model switching**: `POST /api/provider/switch`
- **Channel config**: `POST /api/channel/{name}/config`
- **Plugin reload**: `POST /api/plugins/reload`
- **Token budget**: `POST /api/tokens/budget`
