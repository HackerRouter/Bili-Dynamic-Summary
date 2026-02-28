import hashlib
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests

from .constants import DEFAULT_TIME_FORMAT
from .i18n import t
from .paths import CACHE_DIR


def parse_cookie_string(cookie: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        cookies[k.strip()] = v.strip()
    return cookies


def build_session(cookies: Dict[str, str]) -> requests.Session:
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://t.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
    )
    return session


def _append_media(media: List[str], value: Any) -> None:
    if not value:
        return
    if isinstance(value, str):
        if value not in media:
            media.append(value)
        return
    if isinstance(value, list):
        for v in value:
            _append_media(media, v)
        return
    if isinstance(value, dict):
        for key in ("url", "src", "img_src", "img_url", "cover"):
            if key in value:
                _append_media(media, value.get(key))
        return


def _extract_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, list):
        parts = [_extract_text(x) for x in obj]
        parts = [p for p in parts if p]
        return " ".join(parts).strip()
    if isinstance(obj, dict):
        for key in (
            "text",
            "desc",
            "summary",
            "content",
            "intro",
            "sub_title",
            "subtitle",
            "description",
        ):
            if key in obj:
                value = _extract_text(obj.get(key))
                if value:
                    return value
        if "rich_text_nodes" in obj and isinstance(obj["rich_text_nodes"], list):
            nodes = []
            for n in obj["rich_text_nodes"]:
                if isinstance(n, dict):
                    text = n.get("text") or n.get("raw_text") or ""
                    if text:
                        nodes.append(text)
            if nodes:
                return " ".join(nodes).strip()
    return ""


def _extract_major(major: Dict[str, Any]) -> Tuple[str, str, List[str], str]:
    major_type = major.get("type") or ""
    title = ""
    detail = ""
    media: List[str] = []

    if "archive" in major:
        obj = major["archive"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "ugc_season" in major:
        obj = major["ugc_season"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "pgc" in major:
        obj = major["pgc"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "article" in major:
        obj = major["article"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("covers"))
        _append_media(media, obj.get("cover"))
    if "draw" in major:
        obj = major["draw"] or {}
        detail = _extract_text(obj) or detail
        items = obj.get("items") or []
        for it in items:
            _append_media(media, it.get("src") if isinstance(it, dict) else it)
    if "music" in major:
        obj = major["music"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "common" in major:
        obj = major["common"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "live" in major:
        obj = major["live"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "opus" in major:
        obj = major["opus"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("pics"))
        _append_media(media, obj.get("cover"))

    return major_type, title, media, detail


def _extract_additional(additional: Dict[str, Any]) -> Tuple[str, List[str], str]:
    media: List[str] = []
    title = ""
    detail = ""
    if "ugc" in additional:
        obj = additional["ugc"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "common" in additional:
        obj = additional["common"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "article" in additional:
        obj = additional["article"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("covers"))
        _append_media(media, obj.get("cover"))
    if "music" in additional:
        obj = additional["music"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    if "live" in additional:
        obj = additional["live"] or {}
        title = obj.get("title") or title
        detail = _extract_text(obj) or detail
        _append_media(media, obj.get("cover"))
    return title, media, detail


def _extract_pub_ts(item: Dict[str, Any]) -> int:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    candidates = [
        author.get("pub_ts"),
        author.get("pub_time"),
        author.get("pub_ts"),
        item.get("pub_ts"),
    ]
    for value in candidates:
        try:
            if value:
                return int(value)
        except Exception:
            continue
    return 0


def format_ts(ts: int) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime(DEFAULT_TIME_FORMAT)


def extract_item(item: Dict[str, Any]) -> Dict[str, Any]:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    dynamic = modules.get("module_dynamic") or {}
    desc = _extract_text(dynamic.get("desc") or {})
    major = dynamic.get("major") or {}
    additional = dynamic.get("additional") or {}

    major_type, major_title, major_media, major_detail = _extract_major(major)
    add_title, add_media, add_detail = _extract_additional(additional)

    detail_parts = [desc, major_detail, add_detail]
    detail_parts = [p for p in detail_parts if p]
    merged_text = "\n".join(dict.fromkeys(detail_parts)).strip()

    dyn_id = item.get("id_str") or str(item.get("id") or "")
    url = f"https://t.bilibili.com/{dyn_id}" if dyn_id else ""
    pub_ts = _extract_pub_ts(item)

    info = {
        "id": dyn_id,
        "type": item.get("type") or "",
        "user": author.get("name") or "",
        "user_mid": author.get("mid") or "",
        "text": merged_text,
        "kind": major_type or "",
        "title": major_title or add_title or "",
        "media": major_media + [m for m in add_media if m not in major_media],
        "url": url,
        "pub_ts": pub_ts,
    }

    if item.get("orig"):
        info["orig"] = extract_item(item["orig"])

    return info


def within_range(ts: int, start_ts: int, end_ts: int) -> bool:
    if start_ts and (ts == 0 or ts < start_ts):
        return False
    if end_ts and ts > end_ts:
        return False
    return True


def match_keyword(info: Dict[str, Any], keyword: str) -> bool:
    keyword = (keyword or "").strip()
    if not keyword:
        return True
    text = " ".join(
        [
            str(info.get("title") or ""),
            str(info.get("text") or ""),
            str(info.get("user") or ""),
        ]
    ).lower()
    terms = [term for term in keyword.lower().split() if term]
    return all(term in text for term in terms)


def summarize_text(text: str, limit: int = 80) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def kind_label(kind: str) -> str:
    mapping = {
        "MAJOR_TYPE_ARCHIVE": t("kind_archive"),
        "MAJOR_TYPE_PGC": t("kind_pgc"),
        "MAJOR_TYPE_UGC_SEASON": t("kind_ugc_season"),
        "MAJOR_TYPE_OPUS": t("kind_opus"),
        "MAJOR_TYPE_DRAW": t("kind_draw"),
        "MAJOR_TYPE_ARTICLE": t("kind_article"),
        "MAJOR_TYPE_COMMON": t("kind_common"),
        "MAJOR_TYPE_LIVE": t("kind_live"),
        "MAJOR_TYPE_MUSIC": t("kind_music"),
    }
    return mapping.get(kind, kind or "-")


def mask(value: str) -> str:
    if not value:
        return "-"
    if len(value) <= 6:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _cache_key(settings: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(settings.get("type") or ""),
            str(settings.get("query_mode") or ""),
            str(settings.get("target_up_mids") or ""),
            str(settings.get("pages") or ""),
            str(settings.get("endpoint") or ""),
            str(settings.get("features") or ""),
            str(settings.get("web_location") or ""),
            str(settings.get("sessdata") or ""),
            str(settings.get("cookie") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(key: str):
    return CACHE_DIR / f"{key}.json"


def load_cache(key: str, ttl_minutes: int) -> List[Dict[str, Any]]:
    path = _cache_path(key)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    created_ts = int(data.get("created_ts") or 0)
    if ttl_minutes > 0:
        age = time.time() - created_ts
        if age > ttl_minutes * 60:
            return []
    return data.get("items") or []


def save_cache(key: str, items: List[Dict[str, Any]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    payload = {"created_ts": int(time.time()), "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_page(
    session: requests.Session,
    endpoint: str,
    dynamic_type: str,
    offset: str,
    update_baseline: str,
    features: str,
    web_location: str,
    timeout: int,
) -> Dict[str, Any]:
    params = {
        "type": dynamic_type,
        "offset": offset,
        "update_baseline": update_baseline,
        "features": features,
        "web_location": web_location,
    }
    resp = session.get(endpoint, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fetch_page_with_retry(
    session: requests.Session,
    endpoint: str,
    dynamic_type: str,
    offset: str,
    update_baseline: str,
    features: str,
    web_location: str,
    timeout: int,
    retries: int,
    retry_backoff: float,
    retry_factor: float,
) -> Dict[str, Any]:
    retries = max(0, int(retries))
    delay = max(0.0, float(retry_backoff))
    factor = max(1.0, float(retry_factor))
    max_attempts = retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            data = fetch_page(
                session=session,
                endpoint=endpoint,
                dynamic_type=dynamic_type,
                offset=offset,
                update_baseline=update_baseline,
                features=features,
                web_location=web_location,
                timeout=timeout,
            )
        except Exception as exc:
            if attempt >= max_attempts:
                return {"code": -1, "message": str(exc)}
        else:
            if data.get("code") == 0:
                return data
            if attempt >= max_attempts:
                return data

        if delay > 0:
            time.sleep(delay)
            delay *= factor

    return {"code": -1, "message": t("unknown_error")}


def fetch_dynamics(
    cookie: str,
    sessdata: str,
    dedeuserid: str,
    bili_jct: str,
    dynamic_type: str,
    query_mode: str,
    target_up_mids: str,
    pages: int,
    interactive: bool,
    endpoint: str,
    features: str,
    web_location: str,
    timeout: int,
    start_ts: int,
    end_ts: int,
    keyword: str,
    use_cache: bool,
    cache_ttl: int,
    request_interval: float,
    request_retries: int,
    request_retry_backoff: float,
    request_retry_factor: float,
) -> List[Dict[str, Any]]:
    cookies: Dict[str, str] = {}
    if cookie:
        cookies.update(parse_cookie_string(cookie))
    if sessdata:
        cookies.setdefault("SESSDATA", sessdata)
    if dedeuserid:
        cookies.setdefault("DedeUserID", dedeuserid)
    if bili_jct:
        cookies.setdefault("bili_jct", bili_jct)

    if not cookies:
        raise SystemExit(t("no_cookies"))

    session = build_session(cookies)

    settings_key = _cache_key(
        {
            "type": dynamic_type,
            "query_mode": query_mode,
            "target_up_mids": target_up_mids,
            "pages": pages,
            "endpoint": endpoint,
            "features": features,
            "web_location": web_location,
            "sessdata": cookies.get("SESSDATA", ""),
            "cookie": cookies.get("Cookie", ""),
        }
    )

    collected: List[Dict[str, Any]] = []
    if use_cache:
        collected = load_cache(settings_key, cache_ttl)

    if not collected:
        raw_mode = (query_mode or "all").strip().lower()
        target_mid_set = {x.strip() for x in str(target_up_mids or "").replace(";", ",").split(",") if x.strip()}
        use_selected_up = raw_mode == "selected_up" and bool(target_mid_set)
        offset = ""
        baseline = ""
        durations: List[float] = []
        for page in range(1, pages + 1):
            start_time = time.time()
            data = _fetch_page_with_retry(
                session=session,
                endpoint=endpoint,
                dynamic_type=dynamic_type,
                offset=offset,
                update_baseline=baseline,
                features=features,
                web_location=web_location,
                timeout=timeout,
                retries=request_retries,
                retry_backoff=request_retry_backoff,
                retry_factor=request_retry_factor,
            )
            durations.append(time.time() - start_time)

            if data.get("code") != 0:
                msg = data.get("message") or data.get("msg") or t("unknown_error")
                print(t("request_failed", code=data.get("code"), msg=msg))
                break

            payload = data.get("data") or {}
            items = payload.get("items") or []
            offset = payload.get("offset") or ""
            baseline = payload.get("update_baseline") or baseline
            has_more = payload.get("has_more")

            page_infos: List[Dict[str, Any]] = []
            min_ts = 0
            for item in items:
                info = extract_item(item)
                if info.get("pub_ts"):
                    min_ts = info["pub_ts"] if min_ts == 0 else min(min_ts, info["pub_ts"])
                if use_selected_up and str(info.get("user_mid") or "") not in target_mid_set:
                    continue
                page_infos.append(info)
            collected.extend(page_infos)

            avg = sum(durations) / len(durations)
            remaining = max(0, pages - page)
            eta = int(avg * remaining)
            print(t("page_header", page=page, items=len(items), has_more=has_more))
            print(t("eta_hint", seconds=eta))

            if not has_more:
                break

            if start_ts and min_ts and min_ts < start_ts:
                break

            if interactive and page < pages:
                ans = input(t("page_continue")).strip().lower()
                if ans == "q":
                    break

            if page < pages and request_interval > 0:
                time.sleep(request_interval)

        if use_cache and collected:
            save_cache(settings_key, collected)

    if start_ts or end_ts:
        collected = [x for x in collected if within_range(x.get("pub_ts") or 0, start_ts, end_ts)]

    if keyword:
        collected = [x for x in collected if match_keyword(x, keyword)]

    if not collected:
        print(t("no_data_in_range"))
        return []

    return collected
