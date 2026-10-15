"""Turns a ScanRequest into a safe nmap argv. The preview and the real run both use this."""
from __future__ import annotations

import re

from .catalog import Catalog, OptionSpec
from .environment import Environment
from .models import BuiltCommand, ExplainedPart, ScanRequest
from .targets import TargetError, parse_targets

PORTS_RE = re.compile(r"^\d{1,5}(-\d{1,5})?(,\d{1,5}(-\d{1,5})?)*$")
DURATION_RE = re.compile(r"^\d{1,6}(ms|s|m|h)?$")
BIG_TARGET = 65536
DEFAULT_PORT_COUNT = 1000


class CommandError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def count_ports(spec: str) -> int:
    if not PORTS_RE.match(spec):
        raise ValueError("use ports like 22,80,443 or ranges like 1-1024.")
    total = 0
    for part in spec.split(","):
        lo_text, _, hi_text = part.partition("-")
        lo = int(lo_text)
        hi = int(hi_text) if hi_text else lo
        if not (1 <= lo <= 65535 and 1 <= hi <= 65535):
            raise ValueError("each port must be between 1 and 65535.")
        if hi < lo:
            raise ValueError(f"the range {part} goes backwards.")
        total += hi - lo + 1
    return total


def _selected_options(req: ScanRequest, catalog: Catalog) -> dict[str, str | int | None]:
    selected: dict[str, str | int | None] = {}
    if req.profile_id is not None:
        profile = catalog.profiles.get(req.profile_id)
        if profile is None:
            raise CommandError("profile_id", f"Unknown scan profile '{req.profile_id}'.")
        for po in profile.options:
            selected[po.id] = po.value
    for ov in req.options:
        if ov.id not in catalog.options:
            raise CommandError("options", f"Unknown option '{ov.id}'. Only options shown in the builder can be used.")
        selected[ov.id] = ov.value
    return selected


def _checked_value(spec: OptionSpec, raw: str | int | None) -> str:
    vs = spec.value
    assert vs is not None
    field = f"options.{spec.id}"
    text = str(vs.default if raw is None or str(raw).strip() == "" else raw).strip()
    if vs.type == "int":
        try:
            number = int(text)
        except ValueError:
            raise CommandError(field, f"{spec.label}: '{text}' is not a whole number.") from None
        if (vs.min is not None and number < vs.min) or (vs.max is not None and number > vs.max):
            raise CommandError(field, f"{spec.label}: must be between {vs.min} and {vs.max}.")
        return str(number)
    if vs.type == "ports":
        try:
            count_ports(text)
        except ValueError as exc:
            raise CommandError(field, f"{spec.label}: {exc}") from None
        return text
    if not DURATION_RE.match(text):
        raise CommandError(field, f"{spec.label}: use a number followed by ms, s, m or h, e.g. 30s or 10m.")
    return text


def _render(spec: OptionSpec, value: str | None) -> list[str]:
    if spec.render == "separate":
        return [spec.flag, value or ""]
    if spec.render == "attached":
        return [f"{spec.flag}{value}"]
    return list(spec.expands_to or [spec.flag])


def _port_count(values: dict[str, str | None]) -> int:
    if "all_ports" in values:
        return 65535
    if "ports" in values:
        return count_ports(values["ports"] or "")
    if "top_ports" in values:
        return int(values["top_ports"] or 0)
    if "fast" in values:
        return 100
    return DEFAULT_PORT_COUNT


def _warnings(values: dict[str, str | None], address_count: int) -> list[str]:
    warnings: list[str] = []
    if address_count > BIG_TARGET:
        warnings.append(
            f"This target covers {address_count:,} addresses. A scan this large can take hours; consider a smaller range."
        )
    if "udp_scan" in values:
        ports = _port_count(values)
        if ports > 1000:
            warnings.append(f"UDP scanning {ports:,} ports will be very slow (often hours). Try Top N ports with 20 to 100.")
    timing = values.get("timing")
    if timing == "5":
        warnings.append("Timing 5 (insane) may miss open ports on slower networks.")
    if timing in ("0", "1"):
        warnings.append(f"Timing {timing} is extremely slow: it can take hours even for a single host.")
    if "version_intensity" in values and not ({"service_version", "aggressive"} & values.keys()):
        warnings.append("Version intensity only matters together with version detection (-sV).")
    return warnings


def build_command(req: ScanRequest, env: Environment, catalog: Catalog) -> BuiltCommand:
    try:
        targets = parse_targets(req.target)
    except TargetError as exc:
        raise CommandError("target", str(exc)) from None

    values: dict[str, str | None] = {}
    for oid, raw in _selected_options(req, catalog).items():
        spec = catalog.options[oid]
        if spec.requires_root and not env.can_raw:
            raise CommandError(
                f"options.{oid}",
                f"{spec.label} ({spec.flag}) needs root to send raw packets. "
                "Restart VisualNmap with sudo (./run.sh) to use it.",
            )
        values[oid] = _checked_value(spec, raw) if spec.value else None

    ids = list(values)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = catalog.options[a], catalog.options[b]
            if b in sa.conflicts_with or a in sb.conflicts_with:
                raise CommandError(
                    "options",
                    f"{sa.label} ({sa.flag}) can't be combined with {sb.label} ({sb.flag}). Remove one of them.",
                )

    argv = [env.nmap_path or "nmap"]
    parts: list[ExplainedPart] = []
    emitted_flags: set[str] = set()
    for oid in (o for o in catalog.options if o in values):  # catalog order keeps commands stable
        spec = catalog.options[oid]
        tokens = _render(spec, values[oid])
        if spec.render == "flag":
            tokens = [t for t in tokens if t not in emitted_flags]
            if not tokens:
                continue
            emitted_flags.update(tokens)
        argv += tokens
        parts.append(ExplainedPart(token=" ".join(tokens), text=spec.summary, kind="option"))

    def plumbing(tokens: list[str], text: str) -> None:
        argv.extend(tokens)
        parts.append(ExplainedPart(token=" ".join(tokens), text=text, kind="plumbing"))

    if targets.family == 6:
        plumbing(["-6"], "Scan IPv6 addresses (added automatically because the target is IPv6).")
    if env.can_raw and not env.is_root:
        plumbing(["--privileged"], "Lets nmap use raw packets: this nmap has that permission without root.")
    if "verbose" not in values:
        plumbing(["-v"], "App plumbing: makes nmap report its progress so the dashboard can show it.")
    plumbing(["--stats-every", "2s"], "App plumbing: a progress update every 2 seconds.")
    plumbing(["-oX", "-"], "App plumbing: results as XML so the dashboard can read them.")

    argv += targets.tokens
    noun = "address" if targets.address_count == 1 else "addresses"
    parts.append(
        ExplainedPart(
            token=" ".join(targets.tokens),
            text=f"What to scan: {targets.address_count:,} {noun}.",
            kind="target",
        )
    )
    return BuiltCommand(argv=argv, parts=parts, warnings=_warnings(values, targets.address_count))
