import json
import textwrap
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from .ai_summary import summarize_user_dynamics
from .api import format_ts, kind_label, mask, summarize_text
from .constants import DEFAULT_TIME_FORMAT
from .i18n import t

_UI_WRAP_WIDTH = 76


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


def _match_up_keyword(name: str, mid: str, keyword: str) -> bool:
    kw = (keyword or "").strip().lower()
    if not kw:
        return True
    text = f"{name or ''} {mid or ''}".lower()
    terms = [x for x in kw.split() if x]
    return all(term in text for term in terms)


def _filter_user_list(user_list: List[Tuple[str, str, int]], keyword: str) -> List[Tuple[str, str, int]]:
    if not (keyword or "").strip():
        return user_list
    return [x for x in user_list if _match_up_keyword(x[1], x[0], keyword)]


def set_ui_wrap_width(width: int) -> None:
    global _UI_WRAP_WIDTH
    try:
        value = int(width)
    except Exception:
        return
    # Keep wrapping readable across different terminal sizes.
    _UI_WRAP_WIDTH = max(40, min(200, value))


def require_prompt_toolkit() -> None:
    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        print(t("prompt_toolkit_missing"))
        raise SystemExit(1)


def _create_app(dialog, key_bindings, focus=None):
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout

    layout = Layout(dialog)
    app = Application(layout=layout, key_bindings=key_bindings, full_screen=True)
    if focus is not None:
        try:
            app.layout.focus(focus)
        except Exception:
            pass
    return app


def choose_from_list(title: str, items: List[Tuple[str, str]], text: str = "") -> str:
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import HSplit
    from prompt_toolkit.widgets import Button, Dialog, Label, RadioList

    if not items:
        return ""

    radio = RadioList(values=items)
    try:
        radio.current_value = items[0][0]
    except Exception:
        pass

    result = {"value": ""}

    def ok_handler() -> None:
        result["value"] = radio.current_value or ""
        app.exit()

    body_items = []
    if text:
        body_items.append(Label(text=text))
    body_items.append(radio)

    body = HSplit(body_items, padding=1)
    dialog = Dialog(
        title=title,
        body=body,
        buttons=[Button(text=t("action_ok"), handler=ok_handler)],
        with_background=True,
    )

    kb = KeyBindings()

    @kb.add("escape")
    def _ignore_cancel(event) -> None:
        return

    @kb.add("enter")
    def _accept_on_enter(event) -> None:
        try:
            if event.app.layout.has_focus(radio):
                ok_handler()
        except Exception:
            pass

    app = _create_app(dialog, kb)
    app.run()
    return result.get("value") or ""


def input_text(title: str, text: str, default: str) -> str:
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import HSplit
    from prompt_toolkit.widgets import Button, Dialog, Label, TextArea

    result = {"value": default}

    input_field = TextArea(text=default, multiline=False)

    def ok_handler() -> None:
        result["value"] = input_field.text
        app.exit()

    body = HSplit([Label(text=text), input_field], padding=1)
    dialog = Dialog(
        title=title,
        body=body,
        buttons=[Button(text=t("action_ok"), handler=ok_handler)],
        with_background=True,
    )

    kb = KeyBindings()

    @kb.add("escape")
    def _ignore_cancel(event) -> None:
        return

    @kb.add("enter")
    def _accept_on_enter(event) -> None:
        try:
            if event.app.layout.has_focus(input_field):
                ok_handler()
        except Exception:
            pass

    app = _create_app(dialog, kb, focus=input_field)
    app.run()
    return result.get("value") or default


def detail_view(info: Dict[str, Any]) -> None:
    from prompt_toolkit.shortcuts import button_dialog

    while True:
        lines = []
        lines.append(f"{t('label_user')}: {info.get('user')}({info.get('user_mid')})")
        lines.append(f"{t('label_kind')}: {kind_label(info.get('kind') or '')}")
        lines.append(f"{t('label_id')}: {info.get('id')}")
        lines.append(f"{t('label_time')}: {format_ts(info.get('pub_ts') or 0)}")
        if info.get("title"):
            lines.append(f"{t('label_title')}: {info.get('title')}")
        if info.get("text"):
            lines.append(f"{t('label_text')}: {info.get('text')}")
        if info.get("url"):
            lines.append(f"{t('label_link')}: {info.get('url')}")
        if info.get("media"):
            lines.append(f"{t('label_media')}: {len(info.get('media') or [])}")
        if info.get("orig"):
            lines.append(f"{t('label_forward')}: {info['orig'].get('user')}")

        buttons = [(t("detail_back"), "back")]
        if info.get("url"):
            buttons.insert(0, (t("detail_open_link"), "open_link"))
        if info.get("media"):
            buttons.insert(0, (t("detail_open_media"), "open_media"))

        choice = button_dialog(title=t("detail_title"), text="\n".join(lines), buttons=buttons).run()
        if choice == "open_link":
            import webbrowser

            webbrowser.open(info["url"])
        elif choice == "open_media":
            media_list = [(m, m) for m in info.get("media") or []]
            selected = choose_from_list(t("media_title"), media_list)
            if selected:
                import webbrowser

                webbrowser.open(selected)
        else:
            break


def _show_message(title: str, text: str) -> None:
    choose_from_list(title, [("ok", t("action_ok"))], text=_wrap_text(text, width=_UI_WRAP_WIDTH + 12))


def _wrap_text(value: str, width: int = 0, max_lines: int = 0) -> str:
    if not width or width <= 0:
        width = _UI_WRAP_WIDTH
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return "-"
    lines = textwrap.wrap(
        text,
        width=max(20, int(width)),
        break_long_words=True,
        break_on_hyphens=False,
    )
    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."
    return "\n".join(lines)


def _current_time_range_label(settings: Dict[str, Any]) -> str:
    start = (settings.get("time_from") or "").strip()
    end = (settings.get("time_to") or "").strip()
    if not start and not end:
        return t("time_all")
    return t("time_range_current", start=start or "-", end=end or "-")


def type_label(value: str) -> str:
    mapping = {
        "all": t("type_all"),
        "video": t("type_video"),
        "pgc": t("type_pgc"),
        "article": t("type_article"),
    }
    return mapping.get(value, value)


def sort_label(value: str) -> str:
    mapping = {
        "desc": t("sort_desc"),
        "asc": t("sort_asc"),
    }
    return mapping.get(value, value)


def view_label(value: str) -> str:
    mapping = {
        "summary": t("view_summary"),
        "detail": t("view_detail"),
    }
    return mapping.get(value, value)


def query_mode_label(value: str) -> str:
    mapping = {
        "all": t("query_mode_all"),
        "single_up": t("query_mode_selected_up"),
        "selected_up": t("query_mode_selected_up"),
    }
    return mapping.get((value or "all").lower(), value or "all")


def summary_provider_label(value: str) -> str:
    mapping = {
        "local": t("summary_provider_local"),
        "openai": t("summary_provider_openai"),
        "gemini": t("summary_provider_gemini"),
        "custom_openai": t("summary_provider_custom_openai"),
    }
    return mapping.get((value or "local").lower(), value or "local")


def summary_api_mode_label(value: str) -> str:
    mapping = {
        "chat_completions": t("summary_api_mode_chat_completions"),
        "responses": t("summary_api_mode_responses"),
    }
    return mapping.get((value or "chat_completions").lower(), value or "chat_completions")


def _headers_preview(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    keys = [str(k) for k in value.keys()][:3]
    text = ", ".join(keys)
    if len(value) > 3:
        text += f", +{len(value) - 3}"
    return text


def settings_summary(settings: Dict[str, Any]) -> str:
    lines = [
        t("summary_type", value=type_label(settings.get("type"))),
        t("summary_query_mode", value=query_mode_label(settings.get("query_mode"))),
        t("summary_target_up_mids", value=settings.get("target_up_mids") or settings.get("target_up_mid") or "-"),
        t("summary_pages", value=settings.get("pages")),
        t("summary_page_size", value=settings.get("page_size")),
        t("summary_sort", value=sort_label(settings.get("sort"))),
        t("summary_view", value=view_label(settings.get("view"))),
        t("summary_keyword", value=settings.get("keyword") or "-"),
        t("summary_time_from", value=settings.get("time_from") or "-"),
        t("summary_time_to", value=settings.get("time_to") or "-"),
        t("summary_sessdata", value=mask(settings.get("sessdata") or "")),
        t("summary_cookie", value=t("summary_cookie_provided") if settings.get("cookie") else "-"),
        t("summary_pages_hint"),
        t("summary_cache", value=t("cache_on") if settings.get("cache") else t("cache_off")),
        t("summary_cache_ttl", value=settings.get("cache_ttl")),
        t("summary_auto_save_auth", value=t("cache_on") if settings.get("auto_save_auth") else t("cache_off")),
        t("summary_ai_provider", value=summary_provider_label(settings.get("summary_provider"))),
        t("summary_ai_api_mode", value=summary_api_mode_label(settings.get("summary_api_mode"))),
        t("summary_ai_model", value=settings.get("summary_model") or "-"),
        t("summary_ai_base_url", value=settings.get("summary_base_url") or "-"),
        t("summary_ai_use_json_format", value=t("cache_on") if settings.get("summary_use_json_format", True) else t("cache_off")),
        t("summary_ai_extra_headers", value=_headers_preview(settings.get("summary_extra_headers"))),
        t("summary_ai_max_items", value=settings.get("summary_max_items")),
        t("summary_ai_timeout", value=settings.get("summary_timeout")),
        t("summary_ai_api_key", value=mask(settings.get("summary_api_key") or "")),
    ]
    return "\n".join(lines)


def edit_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    current_type = type_label(settings.get("type"))
    type_choice = choose_from_list(
        t("edit_type_title"),
        [
            ("keep", t("action_keep_with", value=current_type)),
            ("all", t("type_all")),
            ("video", t("type_video")),
            ("pgc", t("type_pgc")),
            ("article", t("type_article")),
        ],
    )
    if type_choice and type_choice != "keep":
        settings["type"] = type_choice

    current_query_mode = query_mode_label(settings.get("query_mode"))
    query_mode_choice = choose_from_list(
        t("edit_query_mode_title"),
        [
            ("keep", t("action_keep_with", value=current_query_mode)),
            ("all", t("query_mode_all")),
            ("selected_up", t("query_mode_selected_up")),
        ],
    )
    if query_mode_choice and query_mode_choice != "keep":
        settings["query_mode"] = query_mode_choice

    target_up_mids = input_text(
        t("edit_target_up_mids_title"),
        t("edit_target_up_mids_prompt"),
        str(settings.get("target_up_mids") or settings.get("target_up_mid") or ""),
    ).strip()
    target_up_mids = _normalize_mid_list(target_up_mids)
    settings["target_up_mids"] = target_up_mids
    settings["target_up_mid"] = target_up_mids.split(",")[0] if target_up_mids else ""

    current_sort = sort_label(settings.get("sort"))
    sort_choice = choose_from_list(
        t("edit_sort_title"),
        [
            ("keep", t("action_keep_with", value=current_sort)),
            ("desc", t("sort_desc")),
            ("asc", t("sort_asc")),
        ],
    )
    if sort_choice and sort_choice != "keep":
        settings["sort"] = sort_choice

    current_view = view_label(settings.get("view"))
    view_choice = choose_from_list(
        t("edit_view_title"),
        [
            ("keep", t("action_keep_with", value=current_view)),
            ("summary", t("view_summary")),
            ("detail", t("view_detail")),
        ],
    )
    if view_choice and view_choice != "keep":
        settings["view"] = view_choice

    pages = input_text(t("edit_pages_title"), t("edit_pages_prompt"), str(settings.get("pages")))
    if pages.isdigit():
        settings["pages"] = max(1, int(pages))

    page_size = input_text(
        t("edit_page_size_title"), t("edit_page_size_prompt"), str(settings.get("page_size"))
    )
    if page_size.isdigit():
        settings["page_size"] = max(1, int(page_size))

    keyword = input_text(
        t("edit_keyword_title"),
        t("edit_keyword_prompt"),
        settings.get("keyword") or "",
    )
    settings["keyword"] = keyword.strip()

    current_cache = t("cache_on") if settings.get("cache") else t("cache_off")
    cache_choice = choose_from_list(
        t("edit_cache_title"),
        [
            ("keep", t("action_keep_with", value=current_cache)),
            ("on", t("cache_on")),
            ("off", t("cache_off")),
        ],
    )
    if cache_choice:
        if cache_choice == "on":
            settings["cache"] = True
        elif cache_choice == "off":
            settings["cache"] = False

    cache_ttl = input_text(
        t("edit_cache_ttl_title"),
        t("edit_cache_ttl_prompt"),
        str(settings.get("cache_ttl") or 60),
    )
    if cache_ttl.isdigit():
        settings["cache_ttl"] = max(0, int(cache_ttl))

    auto_save_choice = choose_from_list(
        t("edit_auto_save_auth_title"),
        [
            (
                "keep",
                t(
                    "action_keep_with",
                    value=t("cache_on") if settings.get("auto_save_auth") else t("cache_off"),
                ),
            ),
            ("on", t("cache_on")),
            ("off", t("cache_off")),
        ],
    )
    if auto_save_choice == "on":
        settings["auto_save_auth"] = True
    elif auto_save_choice == "off":
        settings["auto_save_auth"] = False

    current_summary_provider = summary_provider_label(settings.get("summary_provider"))
    summary_provider = choose_from_list(
        t("edit_summary_provider_title"),
        [
            ("keep", t("action_keep_with", value=current_summary_provider)),
            ("local", t("summary_provider_local")),
            ("openai", t("summary_provider_openai")),
            ("gemini", t("summary_provider_gemini")),
            ("custom_openai", t("summary_provider_custom_openai")),
        ],
    )
    if summary_provider and summary_provider != "keep":
        settings["summary_provider"] = summary_provider

    current_api_mode = summary_api_mode_label(settings.get("summary_api_mode"))
    summary_api_mode = choose_from_list(
        t("edit_summary_api_mode_title"),
        [
            ("keep", t("action_keep_with", value=current_api_mode)),
            ("chat_completions", t("summary_api_mode_chat_completions")),
            ("responses", t("summary_api_mode_responses")),
        ],
    )
    if summary_api_mode and summary_api_mode != "keep":
        settings["summary_api_mode"] = summary_api_mode

    settings["summary_model"] = input_text(
        t("edit_summary_model_title"),
        t("edit_summary_model_prompt"),
        settings.get("summary_model") or "",
    ).strip()

    settings["summary_api_key"] = input_text(
        t("edit_summary_api_key_title"),
        t("edit_summary_api_key_prompt"),
        settings.get("summary_api_key") or "",
    ).strip()

    settings["summary_base_url"] = input_text(
        t("edit_summary_base_url_title"),
        t("edit_summary_base_url_prompt"),
        settings.get("summary_base_url") or "",
    ).strip()

    use_json_choice = choose_from_list(
        t("edit_summary_use_json_format_title"),
        [
            (
                "keep",
                t(
                    "action_keep_with",
                    value=t("cache_on") if settings.get("summary_use_json_format", True) else t("cache_off"),
                ),
            ),
            ("on", t("cache_on")),
            ("off", t("cache_off")),
        ],
    )
    if use_json_choice == "on":
        settings["summary_use_json_format"] = True
    elif use_json_choice == "off":
        settings["summary_use_json_format"] = False

    current_headers = settings.get("summary_extra_headers") or {}
    headers_default = ""
    try:
        if isinstance(current_headers, dict):
            headers_default = json.dumps(current_headers, ensure_ascii=False)
    except Exception:
        headers_default = ""
    headers_raw = input_text(
        t("edit_summary_extra_headers_title"),
        t("edit_summary_extra_headers_prompt"),
        headers_default,
    ).strip()
    if headers_raw:
        try:
            parsed_headers = json.loads(headers_raw)
            if isinstance(parsed_headers, dict):
                settings["summary_extra_headers"] = {str(k): str(v) for k, v in parsed_headers.items()}
            else:
                _show_message(t("summary_notice_title"), t("summary_headers_invalid"))
        except Exception:
            _show_message(t("summary_notice_title"), t("summary_headers_invalid"))
    else:
        settings["summary_extra_headers"] = {}

    summary_max_items = input_text(
        t("edit_summary_max_items_title"),
        t("edit_summary_max_items_prompt"),
        str(settings.get("summary_max_items") or 80),
    ).strip()
    if summary_max_items.isdigit():
        settings["summary_max_items"] = max(1, int(summary_max_items))

    summary_timeout = input_text(
        t("edit_summary_timeout_title"),
        t("edit_summary_timeout_prompt"),
        str(settings.get("summary_timeout") or 45),
    ).strip()
    if summary_timeout.isdigit():
        settings["summary_timeout"] = max(5, int(summary_timeout))

    current_range = _current_time_range_label(settings)
    time_choice = choose_from_list(
        t("time_range_title"),
        [
            ("keep", t("action_keep_with", value=current_range)),
            ("custom", t("time_custom")),
            ("24h", t("time_last_24h")),
            ("7d", t("time_last_7d")),
            ("30d", t("time_last_30d")),
            ("365d", t("time_last_365d")),
            ("year", t("time_this_year")),
            ("all", t("time_all")),
        ],
    )
    now = datetime.now()
    if time_choice == "24h":
        settings["time_from"] = (now - timedelta(hours=24)).strftime(DEFAULT_TIME_FORMAT)
        settings["time_to"] = now.strftime(DEFAULT_TIME_FORMAT)
    elif time_choice == "7d":
        settings["time_from"] = (now - timedelta(days=7)).strftime(DEFAULT_TIME_FORMAT)
        settings["time_to"] = now.strftime(DEFAULT_TIME_FORMAT)
    elif time_choice == "30d":
        settings["time_from"] = (now - timedelta(days=30)).strftime(DEFAULT_TIME_FORMAT)
        settings["time_to"] = now.strftime(DEFAULT_TIME_FORMAT)
    elif time_choice == "365d":
        settings["time_from"] = (now - timedelta(days=365)).strftime(DEFAULT_TIME_FORMAT)
        settings["time_to"] = now.strftime(DEFAULT_TIME_FORMAT)
    elif time_choice == "year":
        start = datetime(now.year, 1, 1, 0, 0)
        settings["time_from"] = start.strftime(DEFAULT_TIME_FORMAT)
        settings["time_to"] = now.strftime(DEFAULT_TIME_FORMAT)
    elif time_choice == "all":
        settings["time_from"] = ""
        settings["time_to"] = ""
    elif time_choice == "custom":
        settings["time_from"] = input_text(
            t("edit_time_from_title"),
            t("edit_time_from_prompt", fmt=DEFAULT_TIME_FORMAT),
            settings.get("time_from") or "",
        )
        settings["time_to"] = input_text(
            t("edit_time_to_title"),
            t("edit_time_to_prompt", fmt=DEFAULT_TIME_FORMAT),
            settings.get("time_to") or "",
        )

    return settings


def settings_menu(settings: Dict[str, Any]) -> str:
    text = settings_summary(settings)
    return choose_from_list(
        t("settings_title"),
        [
            ("start", t("settings_start", text=text)),
            ("edit", t("settings_edit")),
            ("quit", t("settings_quit")),
        ],
    )


def _browse_user_items(items: List[Dict[str, Any]], view_mode: str, page_size: int) -> str:
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page_index = 0

    while True:
        start = page_index * page_size
        end = min(len(items), start + page_size)
        page_items: List[Tuple[str, str]] = []
        for i in range(start, end):
            info = items[i]
            if view_mode == "detail":
                label = f"[{i + 1}] {info.get('title') or ''} | {format_ts(info.get('pub_ts') or 0)}"
                label = summarize_text(label, limit=120)
            else:
                label = t(
                    "list_item_summary",
                    idx=i + 1,
                    title=info.get("title") or "",
                    text=summarize_text(info.get("text") or ""),
                    time=format_ts(info.get("pub_ts") or 0),
                )
            page_items.append((f"item:{i}", label))

        actions: List[Tuple[str, str]] = []
        if page_index + 1 < total_pages:
            actions.append(("next", t("action_next")))
        if page_index > 0:
            actions.append(("prev", t("action_prev")))
        actions.append(("ai_summary", t("action_ai_summary")))
        actions.append(("back", t("action_back")))
        actions.append(("quit", t("action_quit")))

        choice = choose_from_list(
            t("list_page_header", current=page_index + 1, total=total_pages),
            page_items + actions,
            text=t("select_help"),
        )

        if choice == "next":
            page_index += 1
            continue
        if choice == "prev":
            page_index -= 1
            continue
        if choice == "back":
            return "back"
        if choice == "quit":
            return "quit"
        if choice == "ai_summary":
            return "ai_summary"
        if choice and choice.startswith("item:"):
            idx = int(choice.split(":")[1])
            detail_view(items[idx])
            continue


def _browse_sentence_refs(report: Dict[str, Any], sentence_idx: int) -> str:
    sentences = report.get("sentences") or []
    sources = report.get("sources") or []
    if sentence_idx < 0 or sentence_idx >= len(sentences):
        return "back"

    refs = sentences[sentence_idx].get("refs") or []
    while True:
        choices: List[Tuple[str, str]] = []
        for ref in refs:
            source = sources[ref - 1]
            item = source.get("item") or {}
            label = t(
                "summary_ref_item",
                idx=ref,
                time=source.get("time") or "-",
                title=_wrap_text(item.get("title") or source.get("snippet") or "-", width=_UI_WRAP_WIDTH, max_lines=3),
            )
            choices.append((f"ref:{ref}", label))
        choices.append(("back", t("action_back")))
        choices.append(("quit", t("action_quit")))

        choice = choose_from_list(t("summary_refs_title"), choices, text=t("summary_refs_help"))
        if choice == "back":
            return "back"
        if choice == "quit":
            return "quit"
        if choice.startswith("ref:"):
            ref = int(choice.split(":")[1])
            detail_view(sources[ref - 1]["item"])


def _show_ai_summary(user_name: str, items: List[Dict[str, Any]], summary_options: Dict[str, Any]) -> str:
    report = summarize_user_dynamics(
        items=items,
        provider=summary_options.get("provider") or "local",
        api_mode=summary_options.get("api_mode") or "chat_completions",
        model=summary_options.get("model") or "",
        api_key=summary_options.get("api_key") or "",
        base_url=summary_options.get("base_url") or "",
        use_json_format=bool(summary_options.get("use_json_format", True)),
        extra_headers=summary_options.get("extra_headers") or {},
        max_items=int(summary_options.get("max_items") or 80),
        timeout=int(summary_options.get("timeout") or 45),
    )

    error = report.get("error") or ""
    error_detail = (report.get("error_detail") or "").strip()
    if error:
        raw_text = t(
            "summary_notice_raw_error",
            error=error,
            detail=error_detail or t("summary_notice_no_detail"),
        )
        print(f"[AI-SUMMARY-ERROR] {error}: {error_detail or '-'}")
        _show_message(t("summary_notice_title"), raw_text)

    sentences = report.get("sentences") or []
    if not sentences:
        _show_message(t("summary_notice_title"), t("summary_notice_no_result"))
        return "back"

    while True:
        choices: List[Tuple[str, str]] = []
        for idx, row in enumerate(sentences, start=1):
            label = t(
                "summary_sentence_item",
                idx=idx,
                sentence=_wrap_text(row.get("sentence") or "", width=_UI_WRAP_WIDTH),
                refs=len(row.get("refs") or []),
            )
            choices.append((f"sent:{idx - 1}", label))
        choices.append(("back", t("action_back")))
        choices.append(("quit", t("action_quit")))

        text = t(
            "summary_title_text",
            user=user_name,
            provider=summary_provider_label(report.get("provider") or "local"),
        )
        choice = choose_from_list(t("summary_title"), choices, text=text)
        if choice == "back":
            return "back"
        if choice == "quit":
            return "quit"
        if choice.startswith("sent:"):
            sentence_idx = int(choice.split(":")[1])
            sub = _browse_sentence_refs(report, sentence_idx)
            if sub == "quit":
                return "quit"


def browse_users(
    items: List[Dict[str, Any]],
    sort_order: str,
    view_mode: str,
    page_size: int,
    summary_options: Dict[str, Any],
    current_target_up_mids: str = "",
    current_up_filter_keyword: str = "",
) -> Tuple[str, str]:
    by_user: Dict[str, Dict[str, Any]] = {}
    for info in items:
        mid = str(info.get("user_mid") or "")
        name = info.get("user") or "-"
        if mid not in by_user:
            by_user[mid] = {"name": name, "items": []}
        by_user[mid]["items"].append(info)

    user_list = []
    for mid, data in by_user.items():
        user_list.append((mid, data["name"], len(data["items"])))

    reverse = sort_order.lower() == "desc"
    user_list.sort(key=lambda x: x[2], reverse=reverse)
    up_filter_keyword = str(current_up_filter_keyword or "").strip()

    while True:
        filtered_user_list = _filter_user_list(user_list, up_filter_keyword)
        choices = []
        for mid, name, count in filtered_user_list:
            label = t("up_item_label", name=name, mid=mid, count=count)
            choices.append((mid, label))
        if not filtered_user_list:
            choices.append(("no_result", t("choose_up_filter_no_result")))

        choices.append(("filter_up", t("action_filter_up_keyword")))
        choices.append(("clear_filter_up", t("action_clear_up_keyword")))
        choices.append(("set_target_up", t("action_set_target_ups")))
        choices.append(("back", t("action_back")))
        choices.append(("quit", t("action_quit")))

        selected_mid = choose_from_list(
            t("choose_up_title"),
            choices,
            text=t("choose_up_filter_hint", help=t("select_help"), keyword=up_filter_keyword or "-"),
        )
        if selected_mid == "filter_up":
            up_filter_keyword = input_text(
                t("choose_up_filter_title"),
                t("choose_up_filter_prompt"),
                up_filter_keyword,
            ).strip()
            continue
        if selected_mid == "clear_filter_up":
            up_filter_keyword = ""
            continue
        if selected_mid == "no_result":
            continue
        if selected_mid == "set_target_up":
            target_mids, up_filter_keyword = _choose_target_up_mids_from_user_list(
                user_list,
                current_target_up_mids=current_target_up_mids,
                initial_filter_keyword=up_filter_keyword,
            )
            if target_mids == "quit":
                return "quit", up_filter_keyword
            if target_mids and target_mids != "back":
                return f"set_targets:{target_mids}", up_filter_keyword
            continue
        if selected_mid == "back":
            return "back", up_filter_keyword
        if selected_mid == "quit":
            return "quit", up_filter_keyword
        if not selected_mid:
            return "back", up_filter_keyword

        selected = by_user[selected_mid]
        user_items = selected["items"]
        user_items.sort(key=lambda x: x.get("pub_ts") or 0, reverse=True)

        while True:
            result = _browse_user_items(user_items, view_mode=view_mode, page_size=page_size)
            if result == "quit":
                return "quit", up_filter_keyword
            if result == "back":
                break
            if result == "ai_summary":
                sub = _show_ai_summary(
                    user_name=selected.get("name") or "-",
                    items=user_items,
                    summary_options=summary_options,
                )
                if sub == "quit":
                    return "quit", up_filter_keyword


def _choose_target_up_mids_from_user_list(
    user_list: List[Tuple[str, str, int]],
    current_target_up_mids: str = "",
    initial_filter_keyword: str = "",
) -> Tuple[str, str]:
    selected_targets = set(
        mid.strip()
        for mid in _normalize_mid_list(current_target_up_mids).split(",")
        if mid.strip()
    )
    up_filter_keyword = (initial_filter_keyword or "").strip()
    while True:
        filtered_user_list = _filter_user_list(user_list, up_filter_keyword)
        target_choices: List[Tuple[str, str]] = []
        for mid, name, count in filtered_user_list:
            prefix = "[x]" if mid in selected_targets else "[ ]"
            label = f"{prefix} {t('up_item_label', name=name, mid=mid, count=count)}"
            target_choices.append((mid, label))
        if not filtered_user_list:
            target_choices.append(("no_result", t("choose_up_filter_no_result")))
        target_choices.append(("filter_up", t("action_filter_up_keyword")))
        target_choices.append(("clear_filter_up", t("action_clear_up_keyword")))
        target_choices.append(("done", t("action_done")))
        target_choices.append(("clear", t("action_clear_selection")))
        target_choices.append(("skip", t("action_skip_to_settings")))
        target_choices.append(("back", t("action_back")))
        target_choices.append(("quit", t("action_quit")))
        target_mid = choose_from_list(
            t("choose_target_ups_title"),
            target_choices,
            text=t("choose_up_filter_hint", help=t("select_help"), keyword=up_filter_keyword or "-"),
        )
        if target_mid == "quit":
            return "quit", up_filter_keyword
        if target_mid == "filter_up":
            up_filter_keyword = input_text(
                t("choose_up_filter_title"),
                t("choose_up_filter_prompt"),
                up_filter_keyword,
            ).strip()
            continue
        if target_mid == "clear_filter_up":
            up_filter_keyword = ""
            continue
        if target_mid == "no_result":
            continue
        if target_mid == "skip":
            return "skip", up_filter_keyword
        if target_mid == "back":
            return "back", up_filter_keyword
        if target_mid == "clear":
            selected_targets.clear()
            continue
        if target_mid == "done":
            normalized = _normalize_mid_list(",".join(sorted(selected_targets)))
            if not normalized:
                _show_message(t("summary_notice_title"), t("target_up_mids_required"))
                continue
            return normalized, up_filter_keyword
        if target_mid in selected_targets:
            selected_targets.remove(target_mid)
        else:
            selected_targets.add(target_mid)


def choose_target_up_mids(
    items: List[Dict[str, Any]],
    sort_order: str,
    current_target_up_mids: str = "",
    current_up_filter_keyword: str = "",
) -> Tuple[str, str]:
    by_user: Dict[str, Dict[str, Any]] = {}
    for info in items:
        mid = str(info.get("user_mid") or "")
        name = info.get("user") or "-"
        if not mid:
            continue
        if mid not in by_user:
            by_user[mid] = {"name": name, "items": []}
        by_user[mid]["items"].append(info)

    user_list: List[Tuple[str, str, int]] = []
    for mid, data in by_user.items():
        user_list.append((mid, data["name"], len(data["items"])))
    reverse = sort_order.lower() == "desc"
    user_list.sort(key=lambda x: x[2], reverse=reverse)

    if not user_list:
        return "", current_up_filter_keyword
    return _choose_target_up_mids_from_user_list(
        user_list,
        current_target_up_mids=current_target_up_mids,
        initial_filter_keyword=current_up_filter_keyword,
    )


def parse_time_input(value: str, is_end: bool) -> int:
    if not value:
        return 0
    value = value.strip()
    if not value:
        return 0
    fmt_candidates = ["%Y-%m-%d %H:%M:%S", DEFAULT_TIME_FORMAT, "%Y-%m-%d"]
    for fmt in fmt_candidates:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d" and is_end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return int(dt.timestamp())
        except Exception:
            continue
    raise ValueError(t("time_format_error", value=value, fmt=DEFAULT_TIME_FORMAT))


def show_done_dialog() -> str:
    return choose_from_list(t("done_title"), [("back", t("done_back")), ("quit", t("settings_quit"))])






