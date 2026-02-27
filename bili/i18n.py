import json
import locale
from typing import Any, Dict

from .paths import LANG_DIR

_LANG: Dict[str, str] = {}


def _load_json(path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def detect_lang() -> str:
    loc = locale.getdefaultlocale()[0] or ""
    if loc.lower().startswith("zh"):
        return "zh-CN"
    return "en-US"


def _load_lang(lang_code: str) -> Dict[str, str]:
    path = LANG_DIR / f"{lang_code}.json"
    if not path.exists():
        path = LANG_DIR / "en-US.json"
    data = _load_json(path)
    return {str(k): str(v) for k, v in data.items()}


def set_lang(lang_code: str) -> None:
    global _LANG
    _LANG = _load_lang(lang_code)


def t(key: str, **kwargs) -> str:
    text = _LANG.get(key, key)
    try:
        return text.format(**kwargs)
    except Exception:
        return text
