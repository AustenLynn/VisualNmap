"""Detects what the scanner is allowed to do on this machine."""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass

CAP_NET_RAW = 13
# Kali/Debian ship /usr/bin/nmap as a shell wrapper; the real binary (which carries the
# file capabilities) lives here.
KALI_REAL_NMAP = "/usr/lib/nmap/nmap"


@dataclass(frozen=True)
class Environment:
    is_root: bool
    can_raw: bool
    nmap_path: str | None
    nmap_version: str | None
    in_container: bool


def has_cap_net_raw(path: str) -> bool:
    """True if the file's permitted capability set includes CAP_NET_RAW."""
    try:
        data = os.getxattr(path, "security.capability")
    except (OSError, AttributeError):
        return False
    if len(data) < 8:
        return False
    _magic, permitted = struct.unpack("<II", data[:8])
    return bool((permitted >> CAP_NET_RAW) & 1)


def parse_nmap_version(text: str) -> str | None:
    match = re.search(r"Nmap version (\S+)", text)
    return match.group(1) if match else None


def _nmap_version(nmap_path: str) -> str | None:
    try:
        result = subprocess.run([nmap_path, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_nmap_version(result.stdout)


def detect_environment() -> Environment:
    is_root = os.geteuid() == 0
    nmap_path = shutil.which("nmap")
    nmap_version = _nmap_version(nmap_path) if nmap_path else None
    candidates = [p for p in (nmap_path and os.path.realpath(nmap_path), KALI_REAL_NMAP) if p and os.path.exists(p)]
    can_raw = is_root or any(has_cap_net_raw(p) for p in candidates)
    in_container = os.path.exists("/.dockerenv") or os.environ.get("VISUALNMAP_IN_CONTAINER") == "1"
    return Environment(
        is_root=is_root,
        can_raw=can_raw,
        nmap_path=nmap_path,
        nmap_version=nmap_version,
        in_container=in_container,
    )
