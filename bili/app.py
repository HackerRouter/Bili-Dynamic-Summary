import argparse

from .api import fetch_dynamics
from .constants import (
    DEFAULT_ENDPOINT,
    DEFAULT_FEATURES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_WEB_LOCATION,
)
from .i18n import detect_lang, set_lang
from .paths import CONFIG_PATH
from .ui import (
    browse_users,
    edit_settings,
    parse_time_input,
    require_prompt_toolkit,
    set_ui_wrap_width,
    settings_menu,
    show_done_dialog,
)
import json
from typing import Dict


def _load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _persist_auth_to_config(config: Dict[str, object], cookie: str, sessdata: str) -> bool:
    changed = False
    cookie = (cookie or "").strip()
    sessdata = (sessdata or "").strip()
    if cookie and cookie != str(config.get("cookie", "")):
        config["cookie"] = cookie
        changed = True
    if sessdata and sessdata != str(config.get("sessdata", "")):
        config["sessdata"] = sessdata
        changed = True
    if changed:
        _save_json(CONFIG_PATH, config)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Bilibili dynamic feed via web cookie API.")
    parser.add_argument("--cookie", default="", help="Full cookie string.")
    parser.add_argument("--sessdata", default="", help="SESSDATA cookie value.")
    parser.add_argument("--dedeuserid", default="", help="DedeUserID cookie value (mid).")
    parser.add_argument("--bili-jct", default="", help="bili_jct cookie value (CSRF).")
    parser.add_argument("--type", choices=["all", "video", "pgc", "article"], default="all", help="Dynamic feed type.")
    parser.add_argument("--pages", type=int, default=5, help="Max pages to fetch.")
    parser.add_argument("--interactive", action="store_true", help="Prompt before fetching next page.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dynamic feed API endpoint.")
    parser.add_argument("--features", default=DEFAULT_FEATURES, help="features param for feed API.")
    parser.add_argument("--web-location", default=DEFAULT_WEB_LOCATION, help="web_location param.")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout seconds.")
    parser.add_argument("--from", dest="time_from", default="", help="Start time, format: YYYY-MM-DD HH:MM")
    parser.add_argument("--to", dest="time_to", default="", help="End time, format: YYYY-MM-DD HH:MM")
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc", help="Sort UP list by dynamic count.")
    parser.add_argument("--view", choices=["summary", "detail"], default="summary", help="List view mode.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Items per page in list view.")
    parser.add_argument("--lang", default="", help="UI language: auto|zh-CN|en-US (overrides config.json)")
    parser.add_argument("--keyword", default="", help="Keyword filter (space-separated terms).")
    parser.add_argument("--cache", action="store_true", help="Enable cache.")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache.")
    parser.add_argument("--cache-ttl", type=int, default=0, help="Cache TTL minutes (override config).")
    parser.add_argument("--auto-save-auth", action="store_true", help="Auto save latest cookie/sessdata into config.json.")
    parser.add_argument("--no-auto-save-auth", action="store_true", help="Disable auto save latest cookie/sessdata.")
    parser.add_argument(
        "--summary-provider",
        choices=["local", "openai", "gemini", "custom_openai"],
        default="",
        help="AI summary provider.",
    )
    parser.add_argument(
        "--summary-api-mode",
        choices=["chat_completions", "responses"],
        default="",
        help="API mode for OpenAI-compatible providers.",
    )
    parser.add_argument("--summary-model", default="", help="AI summary model.")
    parser.add_argument("--summary-api-key", default="", help="AI summary API key.")
    parser.add_argument("--summary-base-url", default="", help="Base URL for custom_openai provider.")
    parser.add_argument(
        "--summary-use-json-format",
        action="store_true",
        help="Use response_format json_object for chat_completions mode.",
    )
    parser.add_argument(
        "--summary-no-json-format",
        action="store_true",
        help="Disable response_format json_object.",
    )
    parser.add_argument(
        "--summary-extra-headers",
        default="",
        help="Extra headers as JSON object string.",
    )
    parser.add_argument("--summary-max-items", type=int, default=0, help="Max posts used for summary.")
    parser.add_argument("--summary-timeout", type=int, default=0, help="AI summary request timeout seconds.")
    args = parser.parse_args()

    config = _load_json(CONFIG_PATH)
    lang = (args.lang or config.get("lang") or "auto").strip()
    if not lang or lang.lower() == "auto":
        lang = detect_lang()
    set_lang(lang)
    require_prompt_toolkit()
    try:
        set_ui_wrap_width(int(config.get("ui_wrap_width", 76)))
    except Exception:
        set_ui_wrap_width(76)

    cfg_cache = bool(config.get("cache", True))
    cfg_cache_ttl = int(config.get("cache_ttl_minutes", 60))
    cfg_auto_save_auth = bool(config.get("auto_save_auth", False))
    cache_enabled = cfg_cache
    if args.cache:
        cache_enabled = True
    if args.no_cache:
        cache_enabled = False
    auto_save_auth = cfg_auto_save_auth
    if args.auto_save_auth:
        auto_save_auth = True
    if args.no_auto_save_auth:
        auto_save_auth = False
    cache_ttl = args.cache_ttl if args.cache_ttl > 0 else cfg_cache_ttl
    summary_cfg = config.get("summary", {}) if isinstance(config.get("summary"), dict) else {}
    summary_provider = (
        args.summary_provider.strip()
        or str(summary_cfg.get("provider", "")).strip()
        or "local"
    )
    summary_api_mode = (
        args.summary_api_mode.strip()
        or str(summary_cfg.get("api_mode", "")).strip()
        or "chat_completions"
    )
    summary_model = args.summary_model.strip() or str(summary_cfg.get("model", "")).strip()
    summary_api_key = (
        args.summary_api_key.strip()
        or str(summary_cfg.get("api_key", "")).strip()
        or ""
    )
    summary_base_url = (
        args.summary_base_url.strip()
        or str(summary_cfg.get("base_url", "")).strip()
        or ""
    )
    cfg_use_json_format = bool(summary_cfg.get("use_json_format", True))
    summary_use_json_format = cfg_use_json_format
    if args.summary_use_json_format:
        summary_use_json_format = True
    if args.summary_no_json_format:
        summary_use_json_format = False

    summary_extra_headers: Dict[str, str] = {}
    cfg_headers = summary_cfg.get("extra_headers", {})
    if isinstance(cfg_headers, dict):
        summary_extra_headers = {str(k): str(v) for k, v in cfg_headers.items()}
    if args.summary_extra_headers.strip():
        try:
            parsed_headers = json.loads(args.summary_extra_headers)
            if isinstance(parsed_headers, dict):
                summary_extra_headers = {str(k): str(v) for k, v in parsed_headers.items()}
            else:
                print("WARN: --summary-extra-headers is not a JSON object, ignored.")
        except Exception:
            print("WARN: --summary-extra-headers invalid JSON, ignored.")
    summary_max_items = args.summary_max_items if args.summary_max_items > 0 else int(summary_cfg.get("max_items", 80))
    summary_timeout = args.summary_timeout if args.summary_timeout > 0 else int(summary_cfg.get("timeout_seconds", 45))

    settings = {
        "cookie": args.cookie or str(config.get("cookie", "")).strip(),
        "sessdata": args.sessdata or str(config.get("sessdata", "")).strip(),
        "dedeuserid": args.dedeuserid,
        "bili_jct": args.bili_jct,
        "type": args.type,
        "pages": max(1, args.pages),
        "interactive": args.interactive,
        "endpoint": args.endpoint,
        "features": args.features,
        "web_location": args.web_location,
        "timeout": args.timeout,
        "time_from": args.time_from,
        "time_to": args.time_to,
        "sort": args.sort,
        "view": args.view,
        "page_size": max(1, args.page_size),
        "keyword": args.keyword,
        "cache": cache_enabled,
        "cache_ttl": cache_ttl,
        "auto_save_auth": auto_save_auth,
        "summary_provider": summary_provider,
        "summary_api_mode": summary_api_mode,
        "summary_model": summary_model,
        "summary_api_key": summary_api_key,
        "summary_base_url": summary_base_url,
        "summary_use_json_format": bool(summary_use_json_format),
        "summary_extra_headers": summary_extra_headers,
        "summary_max_items": max(1, summary_max_items),
        "summary_timeout": max(5, summary_timeout),
    }

    while True:
        action = settings_menu(settings)
        if action == "quit":
            return
        if action == "edit":
            settings = edit_settings(settings)
            continue
        if action == "start":
            if bool(settings.get("auto_save_auth")):
                try:
                    changed = _persist_auth_to_config(
                        config=config,
                        cookie=settings.get("cookie") or "",
                        sessdata=settings.get("sessdata") or "",
                    )
                    if changed:
                        print("[AUTH-SAVED] cookie/sessdata saved to config.json")
                except Exception as exc:
                    print(f"[AUTH-SAVE-FAILED] {exc}")
            start_ts = parse_time_input(settings.get("time_from") or "", is_end=False) if settings.get("time_from") else 0
            end_ts = parse_time_input(settings.get("time_to") or "", is_end=True) if settings.get("time_to") else 0
            items = fetch_dynamics(
                cookie=settings.get("cookie") or "",
                sessdata=settings.get("sessdata") or "",
                dedeuserid=settings.get("dedeuserid") or "",
                bili_jct=settings.get("bili_jct") or "",
                dynamic_type=settings.get("type") or "all",
                pages=max(1, int(settings.get("pages") or 1)),
                interactive=bool(settings.get("interactive")),
                endpoint=settings.get("endpoint") or DEFAULT_ENDPOINT,
                features=settings.get("features") or DEFAULT_FEATURES,
                web_location=settings.get("web_location") or DEFAULT_WEB_LOCATION,
                timeout=int(settings.get("timeout") or 10),
                start_ts=start_ts,
                end_ts=end_ts,
                keyword=settings.get("keyword") or "",
                use_cache=bool(settings.get("cache")),
                cache_ttl=int(settings.get("cache_ttl") or 60),
            )
            if items:
                result = browse_users(
                    items,
                    sort_order=settings.get("sort") or "desc",
                    view_mode=settings.get("view") or "summary",
                    page_size=max(1, int(settings.get("page_size") or DEFAULT_PAGE_SIZE)),
                    summary_options={
                        "provider": settings.get("summary_provider") or "local",
                        "api_mode": settings.get("summary_api_mode") or "chat_completions",
                        "model": settings.get("summary_model") or "",
                        "api_key": settings.get("summary_api_key") or "",
                        "base_url": settings.get("summary_base_url") or "",
                        "use_json_format": bool(settings.get("summary_use_json_format", True)),
                        "extra_headers": settings.get("summary_extra_headers") or {},
                        "max_items": max(1, int(settings.get("summary_max_items") or 80)),
                        "timeout": max(5, int(settings.get("summary_timeout") or 45)),
                    },
                )
                if result == "quit":
                    return
                continue
            back = show_done_dialog()
            if back == "quit":
                return
            continue


if __name__ == "__main__":
    main()
