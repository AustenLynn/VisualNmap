"""Turns nmap's XML output into ParsedResult. Never raises: bad input gives partial=True."""
from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from .catalog import Catalog
from .models import Host, OsMatch, ParsedResult, Port, ScanStats

_TAG = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)[^<>]*?(/?)>")


def repair_truncated(xml: str) -> str:
    """Drop the incomplete tail and close every tag still open, so a cancelled scan's XML parses."""
    cut = xml.rfind(">")
    if cut == -1:
        return ""
    body = xml[: cut + 1]
    stack: list[str] = []
    for match in _TAG.finditer(body):
        closing, name, self_closing = match.groups()
        if self_closing:
            continue
        if closing:
            if stack and stack[-1] == name:
                stack.pop()
        else:
            stack.append(name)
    return body + "".join(f"</{name}>" for name in reversed(stack))


def _parse_root(xml: str) -> tuple[Element | None, bool]:
    try:
        return fromstring(xml), False
    except (ParseError, DefusedXmlException):
        pass
    repaired = repair_truncated(xml)
    if not repaired:
        return None, True
    try:
        return fromstring(repaired), True
    except (ParseError, DefusedXmlException):
        return None, True


def _host(el: Element, catalog: Catalog) -> Host:
    address = mac = vendor = None
    for addr in el.findall("address"):
        kind = addr.get("addrtype")
        if kind in ("ipv4", "ipv6") and address is None:
            address = addr.get("addr")
        elif kind == "mac":
            mac, vendor = addr.get("addr"), addr.get("vendor")
    status = el.find("status")
    hostname = el.find("hostnames/hostname")
    ports: list[Port] = []
    for p in el.findall("ports/port"):
        number = int(p.get("portid", "0"))
        state = p.find("state")
        service = p.find("service")
        note = catalog.ports.get(number)
        ports.append(
            Port(
                port=number,
                protocol=p.get("protocol", "tcp"),
                state=state.get("state", "unknown") if state is not None else "unknown",
                reason=state.get("reason") if state is not None else None,
                service=service.get("name") if service is not None else None,
                product=service.get("product") if service is not None else None,
                version=service.get("version") if service is not None else None,
                extrainfo=service.get("extrainfo") if service is not None else None,
                note=note.note if note else None,
            )
        )
    os_matches = [
        OsMatch(name=m.get("name", ""), accuracy=int(m.get("accuracy", "0"))) for m in el.findall("os/osmatch")
    ]
    return Host(
        address=address or mac or "unknown",
        hostname=hostname.get("name") if hostname is not None else None,
        mac=mac,
        vendor=vendor,
        status=status.get("state", "unknown") if status is not None else "unknown",
        reason=status.get("reason") if status is not None else None,
        os_matches=os_matches,
        ports=ports,
    )


def parse_nmap_xml(xml: str, catalog: Catalog) -> ParsedResult:
    if not xml.strip():
        return ParsedResult(partial=True)
    root, partial = _parse_root(xml)
    if root is None or root.tag != "nmaprun":
        return ParsedResult(partial=True)
    hosts = [_host(h, catalog) for h in root.iter("host")]
    runstats_hosts = root.find("runstats/hosts")
    finished = root.find("runstats/finished")
    if runstats_hosts is not None:
        stats = ScanStats(
            up=int(runstats_hosts.get("up", "0")),
            down=int(runstats_hosts.get("down", "0")),
            total=int(runstats_hosts.get("total", "0")),
            elapsed_s=float(finished.get("elapsed")) if finished is not None and finished.get("elapsed") else None,
        )
    else:
        partial = True
        up = sum(1 for h in hosts if h.status == "up")
        stats = ScanStats(up=up, down=len(hosts) - up, total=len(hosts))
    return ParsedResult(hosts=hosts, stats=stats, partial=partial)


def open_port_count(result: ParsedResult) -> int:
    return sum(1 for h in result.hosts for p in h.ports if p.state == "open")


def hosts_up_count(result: ParsedResult) -> int:
    return result.stats.up
