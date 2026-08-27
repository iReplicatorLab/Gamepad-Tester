"""Локализация RU/EN."""

from __future__ import annotations

import json

from core.paths import locale_dir
_strings: dict[str, str] = {}
_locale = "ru"


def set_locale(code: str) -> None:
    global _locale, _strings
    _locale = code if code in ("ru", "en") else "ru"
    path = locale_dir() / f"{_locale}.json"
    if path.exists():
        _strings = json.loads(path.read_text(encoding="utf-8"))
    else:
        _strings = {}


def get_locale() -> str:
    return _locale


def t(key: str, **kwargs: object) -> str:
    if not _strings:
        set_locale(_locale)
    text = _strings.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def init_from_config(locale: str) -> None:
    set_locale(locale)
