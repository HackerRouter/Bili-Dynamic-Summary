import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import requests

from .api import format_ts, summarize_text
from .i18n import t


def _safe_text(value: Any) -> str:
    return (str(value or "")).replace("\n", " ").strip()


def _redact_sensitive(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(key=)[^&\\s]+", r"\\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"(Bearer\\s+)[A-Za-z0-9\\-\\._]+", r"\\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"sk-[A-Za-z0-9\\-\\._]+", "sk-***", text)
    return text


def _trim_error(text: str, limit: int = 1000) -> str:
    text = _redact_sensitive(_safe_text(text))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _http_error_detail(exc: requests.exceptions.HTTPError) -> str:
    resp = exc.response
    if resp is None:
        return _trim_error(str(exc))
    status = int(resp.status_code or 0)
    body_text = ""
    try:
        body_text = json.dumps(resp.json(), ensure_ascii=False)
    except Exception:
        body_text = resp.text or ""
    return _trim_error(f"HTTP {status}: {body_text}")


def _tx(key: str, default_text: str, **kwargs) -> str:
    value = t(key, **kwargs)
    if value == key:
        try:
            return default_text.format(**kwargs)
        except Exception:
            return default_text
    return value


def _prepare_sources(items: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    max_items = max(1, int(max_items or 1))
    selected = sorted(items, key=lambda x: int(x.get("pub_ts") or 0), reverse=True)[:max_items]
    sources: List[Dict[str, Any]] = []
    for idx, item in enumerate(selected, start=1):
        title = _safe_text(item.get("title"))
        text = _safe_text(item.get("text"))
        if title and text:
            snippet = f"{title} | {summarize_text(text, 120)}"
        elif title:
            snippet = title
        else:
            snippet = summarize_text(text, 120) or "-"
        sources.append(
            {
                "idx": idx,
                "item": item,
                "snippet": snippet,
                "time": format_ts(int(item.get("pub_ts") or 0)),
            }
        )
    return sources


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    obj_match = re.search(r"(\{[\s\S]*\})", text)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except Exception:
            return {}
    return {}


def _normalize_summary(payload: Dict[str, Any], source_count: int) -> List[Dict[str, Any]]:
    rows = payload.get("summary")
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sentence = _safe_text(row.get("sentence"))
        refs = row.get("refs")
        if not sentence or not isinstance(refs, list):
            continue

        clean_refs: List[int] = []
        for ref in refs:
            try:
                idx = int(ref)
            except Exception:
                continue
            if 1 <= idx <= source_count and idx not in clean_refs:
                clean_refs.append(idx)

        if clean_refs:
            out.append({"sentence": sentence, "refs": clean_refs})
    return out


def _local_summary(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sources:
        return []

    kinds = Counter()
    for src in sources:
        kind = _safe_text(src["item"].get("kind")) or "UNKNOWN"
        kinds[kind] += 1

    summary: List[Dict[str, Any]] = []

    summary.append(
        {
            "sentence": _tx("local_summary_collected", "Collected {count} dynamics in the selected range.", count=len(sources)),
            "refs": [1],
        }
    )

    top_kinds = kinds.most_common(3)
    if top_kinds:
        parts = [f"{k}:{v}" for k, v in top_kinds]
        summary.append(
            {
                "sentence": _tx("local_summary_types", "Main content types are {value}.", value=", ".join(parts)),
                "refs": [idx for idx in range(1, min(5, len(sources)) + 1)],
            }
        )

    latest_refs = [idx for idx in range(1, min(4, len(sources)) + 1)]
    latest_titles = []
    for ref in latest_refs:
        title = _safe_text(sources[ref - 1]["item"].get("title"))
        if title:
            latest_titles.append(summarize_text(title, 50))
    if latest_titles:
        summary.append(
            {
                "sentence": _tx("local_summary_recent", "Recent focus includes: {value}.", value="; ".join(latest_titles)),
                "refs": latest_refs,
            }
        )

    return summary


def _build_prompt(sources: List[Dict[str, Any]]) -> str:
    lines = []
    for src in sources:
        lines.append(f"[{src['idx']}] time={src['time']} | {src['snippet']}")
    joined = "\n".join(lines)

    return (
        "You are an assistant summarizing Bilibili dynamics for one creator. "
        "Given source posts with indices, return strict JSON only.\n"
        "Required format:\n"
        "{\"summary\":[{\"sentence\":\"...\",\"refs\":[1,2]}]}\n"
        "Rules:\n"
        "1) 3-8 concise sentences.\n"
        "2) Every sentence must have refs and refs must only use provided indices.\n"
        "3) Keep statements factual and grounded in sources.\n"
        "4) Do not include markdown, comments, or extra fields.\n"
        "Sources:\n"
        f"{joined}"
    )


def _openai_api_url(base_url: str, api_mode: str) -> str:
    mode = (api_mode or "chat_completions").strip().lower()
    if mode not in ("chat_completions", "responses"):
        mode = "chat_completions"

    base = (base_url or "").strip()
    if not base:
        if mode == "responses":
            return "https://api.openai.com/v1/responses"
        return "https://api.openai.com/v1/chat/completions"
    if base.endswith("/"):
        base = base[:-1]
    lower = base.lower()
    if lower.endswith("/chat/completions") or lower.endswith("/responses"):
        return base
    if mode == "responses":
        return base + "/responses"
    return base + "/chat/completions"


def _extract_responses_text(data: Dict[str, Any]) -> str:
    output_text = _safe_text(data.get("output_text"))
    if output_text:
        return output_text

    chunks: List[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            ptype = _safe_text(part.get("type")).lower()
            if ptype in ("output_text", "text"):
                txt = _safe_text(part.get("text"))
                if txt:
                    chunks.append(txt)
    return "\n".join(chunks).strip()


def _summarize_openai(
    api_key: str,
    model: str,
    prompt: str,
    timeout: int,
    base_url: str = "",
    api_mode: str = "chat_completions",
    use_json_format: bool = True,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    model = model or "gpt-4o-mini"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        for key, value in extra_headers.items():
            if key:
                headers[str(key)] = str(value)

    mode = (api_mode or "chat_completions").strip().lower()
    if mode not in ("chat_completions", "responses"):
        mode = "chat_completions"

    if mode == "responses":
        payload = {
            "model": model,
            "temperature": 0.2,
            "input": prompt,
        }
    else:
        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        if use_json_format:
            payload["response_format"] = {"type": "json_object"}

    url = _openai_api_url(base_url, mode)
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if mode == "responses":
        return _extract_responses_text(data)
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _summarize_gemini(api_key: str, model: str, prompt: str, timeout: int) -> str:
    model = model or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        return ""

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        return ""
    return _safe_text(parts[0].get("text"))


def summarize_user_dynamics(
    items: List[Dict[str, Any]],
    provider: str,
    api_mode: str,
    model: str,
    api_key: str,
    base_url: str,
    use_json_format: bool,
    extra_headers: Dict[str, str],
    max_items: int,
    timeout: int,
) -> Dict[str, Any]:
    sources = _prepare_sources(items, max_items=max_items)
    if not sources:
        return {
            "provider": "local",
            "sources": [],
            "sentences": [],
            "error": "no_data",
            "error_detail": "No source dynamics found.",
        }

    normalized_provider = (provider or "local").strip().lower()
    if normalized_provider in ("", "none"):
        normalized_provider = "local"

    if normalized_provider == "local":
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "",
            "error_detail": "",
        }

    if not api_key:
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "missing_api_key",
            "error_detail": "Missing API key in summary settings.",
        }

    if normalized_provider == "custom_openai" and not (base_url or "").strip():
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "missing_base_url",
            "error_detail": "Missing base_url for custom_openai provider.",
        }

    prompt = _build_prompt(sources)

    try:
        if normalized_provider == "openai":
            raw = _summarize_openai(
                api_key=api_key,
                model=model,
                prompt=prompt,
                timeout=timeout,
                base_url=base_url,
                api_mode=api_mode,
                use_json_format=use_json_format,
                extra_headers=extra_headers,
            )
        elif normalized_provider == "custom_openai":
            raw = _summarize_openai(
                api_key=api_key,
                model=model,
                prompt=prompt,
                timeout=timeout,
                base_url=base_url,
                api_mode=api_mode,
                use_json_format=use_json_format,
                extra_headers=extra_headers,
            )
        elif normalized_provider == "gemini":
            raw = _summarize_gemini(api_key=api_key, model=model, prompt=prompt, timeout=timeout)
        else:
            return {
                "provider": "local",
                "sources": sources,
                "sentences": _local_summary(sources),
                "error": "unknown_provider",
                "error_detail": f"Unknown provider: {normalized_provider}",
            }

        payload = _extract_json(raw)
        sentences = _normalize_summary(payload, source_count=len(sources))
        if sentences:
            return {
                "provider": normalized_provider,
                "sources": sources,
                "sentences": sentences,
                "error": "",
                "error_detail": "",
            }

        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "bad_ai_response",
            "error_detail": _trim_error(raw),
        }
    except requests.exceptions.Timeout as exc:
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "request_timeout",
            "error_detail": _trim_error(str(exc)),
        }
    except requests.exceptions.HTTPError as exc:
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "request_failed",
            "error_detail": _http_error_detail(exc),
        }
    except Exception as exc:
        return {
            "provider": "local",
            "sources": sources,
            "sentences": _local_summary(sources),
            "error": "request_failed",
            "error_detail": _trim_error(repr(exc)),
        }
