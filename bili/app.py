import argparse

from .api import fetch_dynamics
from .constants import (
    DEFAULT_ENDPOINT,
    DEFAULT_FEATURES,
    DEFAULT_PAGES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_QUERY_MODE,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_REQUEST_RETRIES,
    DEFAULT_REQUEST_RETRY_BACKOFF_FACTOR,
    DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS,
    DEFAULT_SORT,
    DEFAULT_TARGET_UP_MIDS,
    DEFAULT_UP_FILTER_KEYWORD,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_VIEW,
    DEFAULT_WEB_LOCATION,
)
from .i18n import detect_lang, set_lang, t
from .paths import CONFIG_PATH
from .ui import (
    browse_users,
    choose_target_up_mids,
    edit_settings,
    parse_time_input,
    require_prompt_toolkit,
    set_ui_wrap_width,
    settings_menu,
    show_done_dialog,
)
import json
from typing import Dict, Optional


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


def _persist_up_filter_keyword_to_config(config: Dict[str, object], up_filter_keyword: str) -> bool:
    defaults = config.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}
        config["defaults"] = defaults
    current = str(defaults.get("up_filter_keyword") or "")
    target = str(up_filter_keyword or "")
    if current == target:
        return False
    defaults["up_filter_keyword"] = target
    _save_json(CONFIG_PATH, config)
    return True


def _as_int(value: object, fallback: int, minimum: Optional[int] = None) -> int:
    try:
        number = int(value)
    except Exception:
        number = fallback
    if minimum is not None:
        number = max(minimum, number)
    return number


def _as_float(value: object, fallback: float, minimum: Optional[float] = None) -> float:
    try:
        number = float(value)
    except Exception:
        number = fallback
    if minimum is not None:
        number = max(minimum, number)
    return number


def _as_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def _normalize_mid_list(raw: str) -> str:
    text = (raw or "").replace(";", ",").replace("|", ",").replace("\n", ",").replace(" ", ",")
    mids = []
    seen = set()
    for part in text.split(","):
        mid = part.strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        mids.append(mid)
    return ",".join(mids)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Bilibili dynamic feed via web cookie API.")
    parser.add_argument("--cookie", default="", help="Full cookie string.")
    parser.add_argument("--sessdata", default="", help="SESSDATA cookie value.")
    parser.add_argument("--dedeuserid", default="", help="DedeUserID cookie value (mid).")
    parser.add_argument("--bili-jct", default="", help="bili_jct cookie value (CSRF).")
    parser.add_argument("--type", choices=["all", "video", "pgc", "article"], default="", help="Dynamic feed type.")
    parser.add_argument("--query-mode", choices=["all", "selected_up"], default="", help="Query mode.")
    parser.add_argument("--target-up-mids", default="", help="Target UP mids for selected_up mode, comma-separated.")
    parser.add_argument("--pages", type=int, default=0, help="Max pages to fetch.")
    parser.add_argument("--interactive", action="store_true", default=None, help="Prompt before fetching next page.")
    parser.add_argument("--endpoint", default="", help="Dynamic feed API endpoint.")
    parser.add_argument("--features", default="", help="features param for feed API.")
    parser.add_argument("--web-location", default="", help="web_location param.")
    parser.add_argument("--timeout", type=int, default=0, help="HTTP timeout seconds.")
    parser.add_argument("--from", dest="time_from", default=None, help="Start time, format: YYYY-MM-DD HH:MM")
    parser.add_argument("--to", dest="time_to", default=None, help="End time, format: YYYY-MM-DD HH:MM")
    parser.add_argument("--sort", choices=["asc", "desc"], default="", help="Sort UP list by dynamic count.")
    parser.add_argument("--view", choices=["summary", "detail"], default="", help="List view mode.")
    parser.add_argument("--page-size", type=int, default=0, help="Items per page in list view.")
    parser.add_argument("--lang", default="", help="UI language: auto|zh-CN|en-US (overrides config.json)")
    parser.add_argument("--keyword", default=None, help="Keyword filter (space-separated terms).")
    parser.add_argument("--cache", action="store_true", help="Enable cache.")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache.")
    parser.add_argument("--cache-ttl", type=int, default=0, help="Cache TTL minutes (override config).")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=-1,
        help="Seconds to sleep between page requests (override config).",
    )
    parser.add_argument(
        "--request-retries",
        type=int,
        default=-1,
        help="Retry times for one page request (override config).",
    )
    parser.add_argument(
        "--request-retry-backoff",
        type=float,
        default=-1,
        help="Initial retry backoff seconds (override config).",
    )
    parser.add_argument(
        "--request-retry-factor",
        type=float,
        default=-1,
        help="Retry backoff factor, >=1.0 (override config).",
    )
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

    defaults_cfg = config.get("defaults", {}) if isinstance(config.get("defaults"), dict) else {}
    fetch_cfg = config.get("fetch", {}) if isinstance(config.get("fetch"), dict) else {}
    summary_cfg = config.get("summary", {}) if isinstance(config.get("summary"), dict) else {}

    default_type = str(defaults_cfg.get("type") or "all").strip().lower()
    if default_type not in {"all", "video", "pgc", "article"}:
        default_type = "all"
    default_query_mode = str(defaults_cfg.get("query_mode") or DEFAULT_QUERY_MODE).strip().lower()
    if default_query_mode not in {"all", "selected_up"}:
        default_query_mode = DEFAULT_QUERY_MODE
    default_target_up_mids = _normalize_mid_list(str(defaults_cfg.get("target_up_mids") or DEFAULT_TARGET_UP_MIDS).strip())
    default_up_filter_keyword = str(defaults_cfg.get("up_filter_keyword") or DEFAULT_UP_FILTER_KEYWORD).strip()
    default_pages = _as_int(defaults_cfg.get("pages"), DEFAULT_PAGES, minimum=1)
    default_interactive = _as_bool(defaults_cfg.get("interactive"), False)
    default_endpoint = str(defaults_cfg.get("endpoint") or DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    default_features = str(defaults_cfg.get("features") or DEFAULT_FEATURES).strip() or DEFAULT_FEATURES
    default_web_location = str(defaults_cfg.get("web_location") or DEFAULT_WEB_LOCATION).strip() or DEFAULT_WEB_LOCATION
    default_timeout = _as_int(defaults_cfg.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS, minimum=1)
    default_sort = str(defaults_cfg.get("sort") or DEFAULT_SORT).strip().lower()
    if default_sort not in {"asc", "desc"}:
        default_sort = DEFAULT_SORT
    default_view = str(defaults_cfg.get("view") or DEFAULT_VIEW).strip().lower()
    if default_view not in {"summary", "detail"}:
        default_view = DEFAULT_VIEW
    default_page_size = _as_int(defaults_cfg.get("page_size"), DEFAULT_PAGE_SIZE, minimum=1)
    default_keyword = str(defaults_cfg.get("keyword") or "").strip()
    default_time_from = str(defaults_cfg.get("time_from") or "").strip()
    default_time_to = str(defaults_cfg.get("time_to") or "").strip()

    cfg_cache = _as_bool(config.get("cache"), True)
    cfg_cache_ttl = _as_int(config.get("cache_ttl_minutes"), 60, minimum=0)
    cfg_auto_save_auth = _as_bool(config.get("auto_save_auth"), False)
    cfg_request_interval = _as_float(
        fetch_cfg.get("request_interval_seconds"),
        DEFAULT_REQUEST_INTERVAL_SECONDS,
        minimum=0.0,
    )
    cfg_request_retries = _as_int(fetch_cfg.get("max_retries"), DEFAULT_REQUEST_RETRIES, minimum=0)
    cfg_request_retry_backoff = _as_float(
        fetch_cfg.get("retry_backoff_seconds"),
        DEFAULT_REQUEST_RETRY_BACKOFF_SECONDS,
        minimum=0.0,
    )
    cfg_request_retry_factor = _as_float(
        fetch_cfg.get("retry_backoff_factor"),
        DEFAULT_REQUEST_RETRY_BACKOFF_FACTOR,
        minimum=1.0,
    )

    dynamic_type = args.type.strip() if args.type else default_type
    query_mode = args.query_mode.strip() if args.query_mode else default_query_mode
    if query_mode not in {"all", "selected_up"}:
        query_mode = default_query_mode
    target_up_mids = _normalize_mid_list(
        args.target_up_mids.strip() if args.target_up_mids else default_target_up_mids
    )
    pages = max(1, args.pages) if args.pages > 0 else default_pages
    interactive = bool(args.interactive) if args.interactive is not None else default_interactive
    endpoint = args.endpoint.strip() if args.endpoint else default_endpoint
    features = args.features.strip() if args.features else default_features
    web_location = args.web_location.strip() if args.web_location else default_web_location
    timeout = max(1, args.timeout) if args.timeout > 0 else default_timeout
    time_from = args.time_from.strip() if isinstance(args.time_from, str) else default_time_from
    time_to = args.time_to.strip() if isinstance(args.time_to, str) else default_time_to
    sort = args.sort.strip() if args.sort else default_sort
    view = args.view.strip() if args.view else default_view
    page_size = max(1, args.page_size) if args.page_size > 0 else default_page_size
    keyword = args.keyword.strip() if isinstance(args.keyword, str) else default_keyword

    request_interval = args.request_interval if args.request_interval >= 0 else cfg_request_interval
    request_retries = args.request_retries if args.request_retries >= 0 else cfg_request_retries
    request_retry_backoff = args.request_retry_backoff if args.request_retry_backoff >= 0 else cfg_request_retry_backoff
    request_retry_factor = max(1.0, args.request_retry_factor) if args.request_retry_factor >= 0 else cfg_request_retry_factor

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
        "type": dynamic_type,
        "query_mode": query_mode,
        "target_up_mids": target_up_mids,
        "up_filter_keyword": default_up_filter_keyword,
        "pages": pages,
        "interactive": interactive,
        "endpoint": endpoint,
        "features": features,
        "web_location": web_location,
        "timeout": timeout,
        "time_from": time_from,
        "time_to": time_to,
        "sort": sort,
        "view": view,
        "page_size": page_size,
        "keyword": keyword,
        "request_interval": max(0.0, request_interval),
        "request_retries": max(0, int(request_retries)),
        "request_retry_backoff": max(0.0, request_retry_backoff),
        "request_retry_factor": max(1.0, float(request_retry_factor)),
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
            def _run_fetch(query_mode_value: str, target_up_mids_value: str) -> list:
                return fetch_dynamics(
                    cookie=settings.get("cookie") or "",
                    sessdata=settings.get("sessdata") or "",
                    dedeuserid=settings.get("dedeuserid") or "",
                    bili_jct=settings.get("bili_jct") or "",
                    dynamic_type=settings.get("type") or "all",
                    query_mode=query_mode_value,
                    target_up_mids=target_up_mids_value,
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
                    request_interval=max(0.0, float(settings.get("request_interval") or 0.0)),
                    request_retries=max(0, int(settings.get("request_retries") or 0)),
                    request_retry_backoff=max(0.0, float(settings.get("request_retry_backoff") or 0.0)),
                    request_retry_factor=max(1.0, float(settings.get("request_retry_factor") or 1.0)),
                )

            mode = settings.get("query_mode") or "all"
            target_mids = str(settings.get("target_up_mids") or "").strip()
            if mode == "selected_up" and not target_mids:
                print(t("target_up_mids_auto_discover"))
                all_items = _run_fetch("all", "")
                if not all_items:
                    back = show_done_dialog()
                    if back == "quit":
                        return
                    continue
                selected_mids, up_filter_keyword = choose_target_up_mids(
                    all_items,
                    sort_order=settings.get("sort") or "desc",
                    current_target_up_mids="",
                    current_up_filter_keyword=str(settings.get("up_filter_keyword") or ""),
                )
                settings["up_filter_keyword"] = up_filter_keyword
                _persist_up_filter_keyword_to_config(config=config, up_filter_keyword=up_filter_keyword)
                if selected_mids == "quit":
                    return
                if selected_mids == "skip":
                    print(t("target_up_mids_selection_skipped"))
                    continue
                if not selected_mids or selected_mids == "back":
                    print(t("target_up_mids_not_set"))
                    continue
                settings["query_mode"] = "selected_up"
                settings["target_up_mids"] = selected_mids
                print(t("target_up_mids_applied", mids=selected_mids))
                target_set = {x.strip() for x in selected_mids.split(",") if x.strip()}
                items = [x for x in all_items if str(x.get("user_mid") or "") in target_set]
            else:
                items = _run_fetch(mode, target_mids)
            if items:
                result, up_filter_keyword = browse_users(
                    items,
                    sort_order=settings.get("sort") or "desc",
                    view_mode=settings.get("view") or "summary",
                    page_size=max(1, int(settings.get("page_size") or DEFAULT_PAGE_SIZE)),
                    current_target_up_mids=str(settings.get("target_up_mids") or ""),
                    current_up_filter_keyword=str(settings.get("up_filter_keyword") or ""),
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
                settings["up_filter_keyword"] = up_filter_keyword
                _persist_up_filter_keyword_to_config(config=config, up_filter_keyword=up_filter_keyword)
                if result == "quit":
                    return
                if result and result.startswith("set_targets:"):
                    target_mids = _normalize_mid_list(result.split(":", 1)[1].strip())
                    if target_mids:
                        settings["query_mode"] = "selected_up"
                        settings["target_up_mids"] = target_mids
                        print(t("target_up_mids_applied", mids=target_mids))
                continue
            back = show_done_dialog()
            if back == "quit":
                return
            continue


if __name__ == "__main__":
    main()
