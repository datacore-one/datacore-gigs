"""Module settings: module.yaml defaults, overridable locally.

Defaults live in module.yaml so the manifest stays the single description of
what the module can be tuned to do. Machine-specific values -- above all the
path to the plur-buzz library, which differs per checkout -- go in
``gigs.local.yaml`` beside it, which is gitignored.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

MODULE_DIR = Path(__file__).resolve().parent.parent
MANIFEST = MODULE_DIR / "module.yaml"
LOCAL = MODULE_DIR / "gigs.local.yaml"


def _defaults() -> dict[str, Any]:
    if not MANIFEST.exists():
        return {}
    data = yaml.safe_load(MANIFEST.read_text()) or {}
    settings = data.get("settings") or {}
    return {k: v.get("default") for k, v in settings.items() if isinstance(v, dict)}


def load() -> dict[str, Any]:
    """Settings, with gigs.local.yaml overriding module.yaml defaults."""
    cfg = _defaults()
    if LOCAL.exists():
        cfg.update(yaml.safe_load(LOCAL.read_text()) or {})
    return cfg


def data_dir(cfg: dict[str, Any] | None = None) -> Path:
    """Where this module's user data lives -- outside the module (DIP-0007).

    A module is publishable; a record of someone's music taste is not. The
    default puts it in the personal space, and it is overridable.
    """
    cfg = cfg or load()
    raw = str(cfg.get("data_dir") or "~/Data/0-personal/.datacore/gigs")
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path
