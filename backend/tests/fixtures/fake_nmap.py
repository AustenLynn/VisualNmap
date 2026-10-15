#!/usr/bin/env python3
"""Stands in for nmap in tests. Behavior is chosen with FAKE_NMAP_MODE."""
import json
import os
import signal
import sys
import time

mode = os.environ.get("FAKE_NMAP_MODE", "ok")
args_file = os.environ.get("FAKE_NMAP_ARGS_FILE")
if args_file:
    with open(args_file, "w") as fh:
        json.dump(sys.argv[1:], fh)

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE nmaprun>\n<nmaprun scanner="nmap" args="fake" version="7.99">\n'
HOST = (
    '<host><status state="up" reason="syn-ack"/>\n<address addr="10.0.0.1" addrtype="ipv4"/>\n'
    '<ports><port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh"/></port>\n'
    "</ports>\n</host>\n"
)
TAIL = '<runstats><finished elapsed="0.20" exit="success"/><hosts up="1" down="0" total="1"/>\n</runstats>\n</nmaprun>\n'


def out(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def err(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


if mode == "stubborn":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

out(HEAD)
out('<taskbegin task="Fake Scan" time="1"/>\n')

if mode in ("slow", "stubborn"):
    time.sleep(30)
    sys.exit(0)

if mode == "fail":
    err('Failed to resolve "nosuchhost.invalid".\nQUITTING!\n')
    sys.exit(1)

if mode == "binary":
    sys.stderr.buffer.write(b"Warning: odd banner \xff\xfe here\n")
    sys.stderr.flush()
    sys.stdout.buffer.write(b"<!-- \xff -->\n")
    sys.stdout.flush()

if mode == "chatty":
    for i in range(50):
        err(f"line {i}\n")

time.sleep(0.05)
out('<taskprogress task="Fake Scan" time="2" percent="50.00" remaining="90" etc="3"/>\n')
err("Warning: fake warning\n")
out('<taskend task="Fake Scan" time="3" extrainfo="1000 total ports"/>\n')
out(HOST)
out(TAIL)
sys.exit(0)
