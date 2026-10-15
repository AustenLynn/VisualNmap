"""Translates nmap's error output and odd results into plain-language hints."""
from __future__ import annotations

import re

from .models import Hint, ParsedResult

_RESOLVE = re.compile(r"Failed to resolve")
_ROOT = re.compile(r"requires root privileges|You requested a scan type which requires root")
_HOST_DOWN = re.compile(r"Host seems down|0 hosts up")
_QUIT = re.compile(r"QUITTING!")


def hints_for(stderr: str, result: ParsedResult | None, status: str, argv: list[str]) -> list[Hint]:
    hints: list[Hint] = []
    if _RESOLVE.search(stderr):
        hints.append(Hint(code="resolve", message="Couldn't find that host name. Check the spelling or try an IP address."))
    if _ROOT.search(stderr):
        hints.append(Hint(code="root", message="This scan needs root. Restart VisualNmap with sudo (./run.sh); see the README."))
    no_hosts = (result is not None and status == "completed" and result.stats.up == 0) or bool(_HOST_DOWN.search(stderr))
    if no_hosts and "-Pn" not in argv and "-sn" not in argv:
        hints.append(
            Hint(
                code="no_hosts",
                message="No hosts answered. Many devices (especially Windows PCs) block ping. "
                "Try again with 'Skip host discovery (-Pn)'.",
                action="retry_with_pn",
            )
        )
    if status == "cancelled":
        hints.append(Hint(code="cancelled", message="You cancelled this scan. The results show only what nmap found before it stopped."))
    if status == "failed" and not hints:
        if _QUIT.search(stderr):
            hints.append(Hint(code="quit", message="Nmap stopped because of an error. See the output above for its message."))
        else:
            hints.append(Hint(code="failed", message="Nmap exited with an error. See the output above for details."))
    return hints
