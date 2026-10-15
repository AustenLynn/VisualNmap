"""Loads and validates the YAML files holding every user-facing explanation."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

CATALOG_DIR = Path(__file__).resolve().parent


class CatalogError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueSpec(_Strict):
    type: Literal["int", "ports", "duration"]
    min: int | None = None
    max: int | None = None
    default: str | int
    placeholder: str | None = None


class OptionSpec(_Strict):
    id: str
    flag: str
    group: str
    label: str
    summary: str
    details: str
    when_to_use: str
    requires_root: bool
    noise: Literal["low", "medium", "high"]
    speed_impact: Literal["none", "slower", "much_slower"]
    example: str
    render: Literal["flag", "separate", "attached"] = "flag"
    value: ValueSpec | None = None
    expands_to: list[str] | None = None
    conflicts_with: list[str] = []


class GroupSpec(_Strict):
    id: str
    label: str
    description: str


class ProfileOption(_Strict):
    id: str
    value: str | int | None = None


class ProfileSpec(_Strict):
    id: str
    title: str
    question: str
    explanation: str
    typical_duration: str
    options: list[ProfileOption]
    requires_root: bool = False


class PortNote(_Strict):
    service: str
    note: str


class Catalog(_Strict):
    groups: list[GroupSpec]
    options: dict[str, OptionSpec]
    profiles: dict[str, ProfileSpec]
    ports: dict[int, PortNote]
    states: dict[str, str]


def _read(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read {path.name}: {exc}") from exc


def _index(items: list, kind: str) -> dict:
    out: dict = {}
    for item in items:
        if item.id in out:
            raise CatalogError(f"duplicate {kind} id: {item.id}")
        out[item.id] = item
    return out


def load_catalog(directory: Path | None = None) -> Catalog:
    directory = directory or CATALOG_DIR
    opts_doc = _read(directory / "options.yaml")
    prof_doc = _read(directory / "profiles.yaml")
    ports_doc = _read(directory / "ports.yaml")
    try:
        groups = [GroupSpec(**g) for g in opts_doc.get("groups", [])]
        options = _index([OptionSpec(**o) for o in opts_doc.get("options", [])], "option")
        profiles = _index([ProfileSpec(**p) for p in prof_doc.get("profiles", [])], "profile")
        ports = {int(k): PortNote(**v) for k, v in (ports_doc.get("ports") or {}).items()}
        states = {str(k): str(v) for k, v in (ports_doc.get("states") or {}).items()}
    except ValidationError as exc:
        raise CatalogError(str(exc)) from exc

    group_ids = {g.id for g in groups}
    for opt in options.values():
        if opt.group not in group_ids:
            raise CatalogError(f"option {opt.id} has unknown group {opt.group}")
        if (opt.render != "flag") != (opt.value is not None):
            raise CatalogError(f"option {opt.id}: value is required exactly when render is separate/attached")
        for other in opt.conflicts_with:
            if other not in options:
                raise CatalogError(f"option {opt.id} conflicts with unknown option {other}")
    for port in ports:
        if not 1 <= port <= 65535:
            raise CatalogError(f"port {port} out of range")
    for pid, profile in list(profiles.items()):
        for po in profile.options:
            if po.id not in options:
                raise CatalogError(f"profile {pid} uses unknown option {po.id}")
        needs_root = any(options[po.id].requires_root for po in profile.options)
        profiles[pid] = profile.model_copy(update={"requires_root": needs_root})

    return Catalog(groups=groups, options=options, profiles=profiles, ports=ports, states=states)
