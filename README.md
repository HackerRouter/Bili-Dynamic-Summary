# BiliDynamicSummary

A prompt_toolkit-based TUI to fetch and browse your Bilibili dynamic feed (videos, posts, articles) using web cookies.

## Features
- Time range filter (custom / last 24h / 7d / 30d / 365d / this year / all)
- Keyword filter (space-separated terms, AND logic)
- Sort UPs by dynamic count (asc/desc)
- Summary or detail list view
- Pagination for long lists
- Cache with TTL to reduce repeated requests
- AI summary per UP with sentence-to-post references
- Bilingual UI (zh-CN / en-US, auto-detect)

## Requirements
- Python 3.8+
- `requests`
- `prompt_toolkit`

Install dependencies:
```powershell
python -m pip install requests prompt_toolkit
```

## Quick Start
```powershell
python BiliDynamicSummary.py --sessdata "YOUR_SESSDATA"
```

You can also pass the full cookie string:
```powershell
python BiliDynamicSummary.py --cookie "SESSDATA=...; DedeUserID=...; bili_jct=..."
```

## UI Flow
1. **Current settings** dialog
2. **Edit settings** (optional)
3. **Start** to fetch
4. **Select UP** from list (sorted by dynamic count)
5. **Browse dynamics** with paging and detail view
6. In a selected UP list, choose **AI Summary** to generate summary sentences and drill down to referenced posts

## Keyboard
- Up/Down: select
- Enter: confirm
- Tab: switch focus

## Settings Explained
- `type`: filter by dynamic type (`all`, `video`, `pgc`, `article`)
- `pages`: max number of pages to request from the API
- `page_size`: number of items per page in the list view
- `sort`: sort UP list by count (`desc` or `asc`)
- `view`: list mode (`summary` or `detail`)
- `keyword`: space-separated terms, all terms must match
- `time_from`, `time_to`: filter by publish time
- `cache`: enable/disable cache
- `cache_ttl`: cache validity in minutes
- `summary_provider`: `local`, `openai`, `gemini`, or `custom_openai`
- `summary_api_mode`: `chat_completions` or `responses` (OpenAI-compatible providers)
- `summary_model`: model name for the selected provider
- `summary_api_key`: API key (optional for `local`)
- `summary_base_url`: base URL for `custom_openai` provider
- `summary_use_json_format`: whether to send `response_format=json_object` in `chat_completions` mode
- `summary_extra_headers`: extra headers (JSON object) for AI requests
- `summary_max_items`: max number of posts used for one summary
- `summary_timeout`: timeout seconds for AI summary requests

### About `pages`
The API is page-based. `pages` controls how many pages are fetched at most. Larger time ranges generally need a higher `pages` value to collect all results.

## Time Format
Custom time input accepts:
- `YYYY-MM-DD HH:MM`
- `YYYY-MM-DD HH:MM:SS`
- `YYYY-MM-DD`

## Cache
Cache is stored in `cache/`. Enable/disable and set TTL in the UI or `config.json`:
```json
{
  "lang": "auto",
  "cookie": "",
  "sessdata": "",
  "ui_wrap_width": 60,
  "cache": true,
  "cache_ttl_minutes": 60,
  "auto_save_auth": false,
  "summary": {
    "provider": "local",
    "api_mode": "chat_completions",
    "model": "",
    "api_key": "",
    "base_url": "",
    "use_json_format": true,
    "extra_headers": {},
    "max_items": 80,
    "timeout_seconds": 45
  }
}
```

### `config.json` field reference
- `lang`: `auto` | `zh-CN` | `en-US`. `auto` selects by system locale.
- `cookie`: full cookie string (optional). If empty, you can still provide `--cookie`.
- `sessdata`: SESSDATA value (optional). If empty, you can still provide `--sessdata`.
- `ui_wrap_width`: preferred line-wrap width for long UI text blocks (range clamped to `40..200`).
- `cache`: `true` or `false`. Controls whether fetched dynamics are read from/saved to local cache.
- `cache_ttl_minutes`: cache expiration in minutes. `<= 0` means no expiration check.
- `auto_save_auth`: auto-save latest `cookie`/`sessdata` into `config.json` (`false` by default).
- `summary.provider`: `local` | `openai` | `gemini` | `custom_openai`.
- `summary.api_mode`: `chat_completions` | `responses` for OpenAI-compatible providers.
- `summary.model`: model name for selected provider, e.g. `gpt-4o-mini`, `gemini-1.5-flash`.
- `summary.api_key`: API key used by `openai` or `gemini`.
- `summary.base_url`: base URL for `custom_openai` (OpenAI-compatible API), e.g. `https://api.xxx.com/v1`.
- `summary.use_json_format`: send `response_format={"type":"json_object"}` in `chat_completions`.
- `summary.extra_headers`: JSON object merged into request headers, e.g. `{"x-channel":"kiro"}`.
- `summary.max_items`: max number of dynamics used as AI summary input.
- `summary.timeout_seconds`: HTTP timeout for AI summary requests.

## CLI Options
```text
--cookie         Full cookie string
--sessdata       SESSDATA value
--dedeuserid     DedeUserID value (mid)
--bili-jct       bili_jct value (CSRF)
--type           all | video | pgc | article
--pages          Max pages to fetch
--page-size      Items per page in list view
--from           Start time (YYYY-MM-DD HH:MM)
--to             End time (YYYY-MM-DD HH:MM)
--sort           asc | desc
--view           summary | detail
--keyword        Keyword filter
--cache          Enable cache
--no-cache       Disable cache
--cache-ttl      Cache TTL minutes (override config)
--auto-save-auth Enable auto save latest cookie/sessdata
--no-auto-save-auth Disable auto save latest cookie/sessdata
--summary-provider  local | openai | gemini | custom_openai
--summary-api-mode  chat_completions | responses
--summary-model     AI model name
--summary-api-key   API key for AI provider
--summary-base-url  Base URL for custom_openai
--summary-use-json-format Enable response_format json_object
--summary-no-json-format  Disable response_format json_object
--summary-extra-headers   JSON object string for extra headers
--summary-max-items Max posts used in one summary
--summary-timeout   AI summary timeout seconds
--lang           auto | zh-CN | en-US
--interactive    Prompt before fetching next page
```

## Project Layout
```
BiliDynamicSummary.py       # Entry point
bili/
  app.py                    # Main flow
  api.py                    # Fetch/parse/cache
  ai_summary.py             # AI summary adapters and fallback
  ui.py                     # TUI dialogs
  i18n.py                   # Language loader
  constants.py              # Constants
  paths.py                  # Paths
langs/
  zh-CN.json
  en-US.json
config.json
cache/
```

## Notes
- This tool requires valid cookies from a logged-in Bilibili session.
- If you are on Windows Terminal, Ctrl+Click a URL to open it in your browser.
- If API key is missing or AI response fails, the app falls back to local summary automatically.

## Disclaimer
- Use this tool only for personal learning or lawful analysis.
- You are responsible for complying with Bilibili Terms of Service and local laws.
- Do not share or commit sensitive credentials (`cookie`, `sessdata`, API keys).
- AI summaries may be incomplete or incorrect; verify against original dynamics before making decisions.
