"""Validates what the user typed in the target box. Nothing that fails here reaches nmap."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

MAX_TOKENS = 16
EXAMPLES = "e.g. 192.168.1.1, 192.168.1.0/24, 192.168.1.10-50 or scanme.nmap.org"
_RANGE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})-(\d{1,3})$")
_HOSTNAME = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTargets:
    tokens: list[str]
    address_count: int
    family: int  # 4 or 6


def parse_targets(text: str) -> ParsedTargets:
    tokens = text.split()
    if not tokens:
        raise TargetError(f"Enter something to scan, {EXAMPLES}.")
    if len(tokens) > MAX_TOKENS:
        raise TargetError(f"Too many targets ({len(tokens)}). The limit is {MAX_TOKENS}; use a range or CIDR instead.")
    total = 0
    families: set[int] = set()
    for token in tokens:
        count, family = _classify(token)
        total += count
        families.add(family)
    if len(families) > 1:
        raise TargetError("Can't mix IPv4 and IPv6 targets in one scan (nmap scans one family at a time). Run two scans.")
    return ParsedTargets(tokens=tokens, address_count=total, family=families.pop())


def _classify(token: str) -> tuple[int, int]:
    if token.startswith("-"):
        raise TargetError(f"'{token}' looks like an nmap option, not a target. Use {EXAMPLES}.")
    if "/" in token:
        try:
            net = ipaddress.IPv4Network(token, strict=False)
        except ValueError:
            raise TargetError(f"'{token}' is not a valid IPv4 network. Use {EXAMPLES}.") from None
        if not 8 <= net.prefixlen <= 32:
            raise TargetError(f"'{token}': the network size must be between /8 and /32.")
        return net.num_addresses, 4
    match = _RANGE.match(token)
    if match:
        a, b, c, start, end = (int(g) for g in match.groups())
        if max(a, b, c, start, end) > 255 or end < start:
            raise TargetError(f"'{token}' is not a valid range. The last number must count up, e.g. 192.168.1.10-50.")
        return end - start + 1, 4
    try:
        ipaddress.IPv4Address(token)
        return 1, 4
    except ValueError:
        pass
    if ":" in token:
        try:
            ipaddress.IPv6Address(token)
            return 1, 6
        except ValueError:
            raise TargetError(f"'{token}' is not a valid IPv6 address.") from None
    last_label = token.rsplit(".", 1)[-1]
    if len(token) <= 253 and _HOSTNAME.match(token) and any(ch.isalpha() for ch in last_label):
        return 1, 4
    raise TargetError(f"'{token}' is not a valid target. Use {EXAMPLES}.")
