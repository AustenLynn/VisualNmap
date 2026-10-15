import os

import pytest

from visualnmap import environment
from visualnmap.environment import Environment, detect_environment, has_cap_net_raw, parse_nmap_version

# Real xattr captured from Kali's /usr/lib/nmap/nmap (cap_net_bind_service,cap_net_admin,cap_net_raw=eip)
KALI_CAPS = bytes.fromhex("0100000200340000003400000000000000000000")
# Same layout with only cap_net_bind_service (bit 10) set
NO_RAW_CAPS = bytes.fromhex("0100000200040000000400000000000000000000")


def test_parse_nmap_version():
    assert parse_nmap_version("Nmap version 7.99 ( https://nmap.org )\nPlatform: x86_64") == "7.99"
    assert parse_nmap_version("garbage") is None


def test_has_cap_net_raw_true_for_kali_caps(monkeypatch):
    monkeypatch.setattr(os, "getxattr", lambda path, name: KALI_CAPS)
    assert has_cap_net_raw("/whatever") is True


def test_has_cap_net_raw_false_without_raw_bit(monkeypatch):
    monkeypatch.setattr(os, "getxattr", lambda path, name: NO_RAW_CAPS)
    assert has_cap_net_raw("/whatever") is False


def test_has_cap_net_raw_false_when_no_xattr(tmp_path):
    f = tmp_path / "plain"
    f.write_text("x")
    assert has_cap_net_raw(str(f)) is False


def test_detect_environment_without_nmap(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setattr(environment.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(environment, "KALI_REAL_NMAP", "/nonexistent/nmap")
    monkeypatch.delenv("VISUALNMAP_IN_CONTAINER", raising=False)
    env = detect_environment()
    assert env.nmap_path is None
    assert env.nmap_version is None
    assert env.is_root is False
    assert env.can_raw is False


def test_detect_environment_root_implies_can_raw(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setattr(environment.os, "geteuid", lambda: 0)
    env = detect_environment()
    assert env.is_root is True and env.can_raw is True


def test_detect_environment_container_flag(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setenv("VISUALNMAP_IN_CONTAINER", "1")
    assert detect_environment().in_container is True


def test_environment_is_frozen():
    env = Environment(is_root=False, can_raw=False, nmap_path=None, nmap_version=None, in_container=False)
    with pytest.raises(Exception):
        env.is_root = True  # type: ignore[misc]
