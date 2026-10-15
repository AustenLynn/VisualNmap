from visualnmap.errors import hints_for
from visualnmap.models import Host, ParsedResult, ScanStats

UP = ParsedResult(hosts=[Host(address="10.0.0.1", status="up")], stats=ScanStats(up=1, total=1))
NONE_UP = ParsedResult(hosts=[], stats=ScanStats(up=0, down=256, total=256))
ARGV = ["nmap", "-F", "-v", "--stats-every", "2s", "-oX", "-", "10.0.0.1"]


def codes(hints):
    return [h.code for h in hints]


def test_failed_to_resolve():
    hints = hints_for('Failed to resolve "nosuchhost.invalid".\n', NONE_UP, "completed", ARGV)
    assert "resolve" in codes(hints)
    assert "spelling" in hints[codes(hints).index("resolve")].message


def test_requires_root():
    stderr = "You requested a scan type which requires root privileges.\nQUITTING!\n"
    hints = hints_for(stderr, None, "failed", ARGV)
    assert codes(hints)[0] == "root"
    assert "quit" not in codes(hints)  # root hint already explains the quit
    assert "failed" not in codes(hints)


def test_no_hosts_up_offers_retry_with_pn():
    hints = hints_for("", NONE_UP, "completed", ARGV)
    assert codes(hints) == ["no_hosts"]
    assert hints[0].action == "retry_with_pn"


def test_host_seems_down_message_also_triggers_no_hosts():
    hints = hints_for("Note: Host seems down. If it is really up, but blocking our ping probes, try -Pn\n", NONE_UP, "completed", ARGV)
    assert codes(hints) == ["no_hosts"]


def test_no_retry_hint_when_pn_already_used():
    argv = ARGV[:1] + ["-Pn"] + ARGV[1:]
    assert hints_for("", NONE_UP, "completed", argv) == []


def test_no_retry_hint_for_ping_scan_with_hosts():
    assert hints_for("", UP, "completed", ARGV) == []


def test_generic_quit():
    hints = hints_for("Something odd happened\nQUITTING!\n", None, "failed", ARGV)
    assert codes(hints) == ["quit"]


def test_generic_failure():
    assert codes(hints_for("", None, "failed", ARGV)) == ["failed"]


def test_cancelled():
    hints = hints_for("", UP, "cancelled", ARGV)
    assert codes(hints) == ["cancelled"]
