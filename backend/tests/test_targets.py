import pytest

from visualnmap.targets import TargetError, parse_targets


@pytest.mark.parametrize(
    "text,count,family",
    [
        ("192.168.1.1", 1, 4),
        ("192.168.1.0/24", 256, 4),
        ("10.0.0.0/8", 16777216, 4),
        ("192.168.1.10-50", 41, 4),
        ("scanme.nmap.org", 1, 4),
        ("localhost", 1, 4),
        ("10.0.0.1 10.0.0.2", 2, 4),
        ("::1", 1, 6),
        ("fe80::1 2001:db8::5", 2, 6),
    ],
)
def test_valid_targets(text, count, family):
    parsed = parse_targets(text)
    assert parsed.address_count == count
    assert parsed.family == family
    assert parsed.tokens == text.split()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-iL /etc/shadow",
        "--script=vuln",
        "-oN /etc/x",
        "; rm -rf /",
        "$(id)",
        "192.168.1.1;id",
        "`id`",
        "999.1.1.1",
        "192.168.1.0/7",
        "192.168.1.0/33",
        "192.168.1.50-10",
        "192.168.1.1-300",
        "::zz",
        "a_b.example.com",
        " ".join(f"10.0.0.{i}" for i in range(1, 18)),  # 17 tokens
    ],
)
def test_invalid_targets(text):
    with pytest.raises(TargetError):
        parse_targets(text)


def test_mixed_ip_families_rejected():
    with pytest.raises(TargetError, match="IPv4 and IPv6"):
        parse_targets("192.168.1.1 ::1")


def test_error_message_gives_examples():
    with pytest.raises(TargetError, match="192.168.1.0/24"):
        parse_targets("not a target!")
