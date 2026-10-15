from pathlib import Path

from visualnmap.parser import hosts_up_count, open_port_count, parse_nmap_xml, repair_truncated

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_services_host_details(catalog):
    result = parse_nmap_xml(load("services.xml"), catalog)
    assert result.partial is False
    assert len(result.hosts) == 1
    host = result.hosts[0]
    assert host.address == "192.168.1.10"
    assert host.hostname == "pi.lan"
    assert host.mac == "AA:BB:CC:DD:EE:FF"
    assert host.vendor == "Raspberry Pi Foundation"
    assert host.status == "up"
    assert host.reason == "arp-response"
    assert [m.accuracy for m in host.os_matches] == [96, 93]
    assert host.os_matches[0].name == "Linux 5.0 - 5.14"


def test_services_ports_and_notes(catalog):
    host = parse_nmap_xml(load("services.xml"), catalog).hosts[0]
    by_port = {p.port: p for p in host.ports}
    assert set(by_port) == {22, 80, 445}
    ssh = by_port[22]
    assert (ssh.protocol, ssh.state, ssh.reason, ssh.service) == ("tcp", "open", "syn-ack", "ssh")
    assert ssh.product == "OpenSSH"
    assert ssh.version == "8.9p1 Ubuntu 3ubuntu0.10"
    assert ssh.extrainfo == "Ubuntu Linux; protocol 2.0"
    assert "SSH" in (ssh.note or "")
    assert by_port[445].state == "filtered"
    assert by_port[445].product is None


def test_stats(catalog):
    result = parse_nmap_xml(load("services.xml"), catalog)
    assert (result.stats.up, result.stats.down, result.stats.total) == (1, 0, 1)
    assert result.stats.elapsed_s == 12.5
    assert open_port_count(result) == 2
    assert hosts_up_count(result) == 1


def test_multiple_hosts_and_down_host(catalog):
    result = parse_nmap_xml(load("multi.xml"), catalog)
    assert [h.status for h in result.hosts] == ["up", "down"]
    assert result.hosts[0].hostname == "router.lan"
    assert result.hosts[1].hostname is None
    assert result.hosts[0].ports == []
    assert (result.stats.up, result.stats.down, result.stats.total) == (1, 1, 2)


def test_zero_hosts(catalog):
    result = parse_nmap_xml(load("zero_hosts.xml"), catalog)
    assert result.hosts == []
    assert result.stats.total == 256 and result.stats.up == 0
    assert result.partial is False


def test_truncated_xml_is_partial_but_keeps_data(catalog):
    xml = load("services.xml")
    cut = xml.index('<port protocol="tcp" portid="80">') + 20  # cut inside the second port's tag
    result = parse_nmap_xml(xml[:cut], catalog)
    assert result.partial is True
    assert len(result.hosts) == 1
    assert [p.port for p in result.hosts[0].ports] == [22]
    assert result.stats.up == 1  # derived from hosts when runstats is missing


def test_garbage_and_empty_input(catalog):
    for text in ("", "   ", "not xml at all", "<nmaprun"):
        result = parse_nmap_xml(text, catalog)
        assert result.partial is True
        assert result.hosts == []


def test_entity_expansion_is_refused(catalog):
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        "<nmaprun>&lol2;</nmaprun>"
    )
    result = parse_nmap_xml(bomb, catalog)
    assert result.partial is True and result.hosts == []


def test_repair_truncated():
    assert repair_truncated("<a><b x='1'><c/><d attr") == "<a><b x='1'><c/></b></a>"
    assert repair_truncated('<?xml version="1.0"?><a><b>text</b>') == '<?xml version="1.0"?><a><b>text</b></a>'
    assert repair_truncated("no tags") == ""
