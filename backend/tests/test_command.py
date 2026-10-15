import pytest

from visualnmap.command import CommandError, build_command, count_ports
from visualnmap.environment import Environment
from visualnmap.models import OptionValue, ScanRequest

NMAP = "/usr/bin/nmap"
PLUMBING = ["-v", "--stats-every", "2s", "-oX", "-"]


def env(root: bool = True, raw: bool | None = None) -> Environment:
    return Environment(
        is_root=root,
        can_raw=root if raw is None else raw,
        nmap_path=NMAP,
        nmap_version="7.99",
        in_container=False,
    )


def req(target="192.168.1.10", profile=None, **opts) -> ScanRequest:
    return ScanRequest(
        target=target,
        profile_id=profile,
        options=[OptionValue(id=k, value=v) for k, v in opts.items()],
    )


def test_quick_ports_profile_argv(catalog):
    built = build_command(req(profile="quick_ports"), env(), catalog)
    assert built.argv == [NMAP, "-F", "-T4", *PLUMBING, "192.168.1.10"]


def test_every_profile_builds_as_root(catalog):
    for pid in catalog.profiles:
        build_command(req(profile=pid), env(), catalog)


def test_user_option_overrides_profile_value(catalog):
    built = build_command(req(profile="quick_ports", timing=2), env(), catalog)
    assert "-T2" in built.argv and "-T4" not in built.argv


def test_separate_and_attached_values(catalog):
    built = build_command(req(ports="22,80", syn_ping="443", max_retries=1), env(), catalog)
    assert built.argv[1:7] == ["-PS443", "-p", "22,80", "--max-retries", "1", "-v"]


def test_missing_value_uses_default(catalog):
    built = build_command(req(top_ports=None), env(), catalog)
    assert built.argv[1:3] == ["--top-ports", "200"]


def test_unknown_option_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(script="vuln"), env(), catalog)
    assert exc.value.field == "options"


def test_unknown_profile_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(profile="nope"), env(), catalog)
    assert exc.value.field == "profile_id"


def test_root_option_rejected_without_raw(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(syn_scan=None), env(root=False), catalog)
    assert exc.value.field == "options.syn_scan"
    assert "sudo" in exc.value.message


def test_root_option_allowed_with_caps_adds_privileged(catalog):
    built = build_command(req(syn_scan=None), env(root=False, raw=True), catalog)
    assert "-sS" in built.argv
    assert "--privileged" in built.argv


def test_root_does_not_add_privileged(catalog):
    assert "--privileged" not in build_command(req(syn_scan=None), env(), catalog).argv


def test_conflicting_options_rejected(catalog):
    with pytest.raises(CommandError, match="can't be combined"):
        build_command(req(ping_only=None, ports="80"), env(), catalog)


def test_two_tcp_techniques_rejected(catalog):
    with pytest.raises(CommandError):
        build_command(req(syn_scan=None, connect_scan=None), env(), catalog)


def test_udp_plus_syn_allowed(catalog):
    built = build_command(req(syn_scan=None, udp_scan=None, ports="53"), env(), catalog)
    assert "-sS" in built.argv and "-sU" in built.argv


@pytest.mark.parametrize("spec", ["0", "65536", "1-", "a", "100-10", "22,,80", "-"])
def test_bad_port_specs_rejected(catalog, spec):
    with pytest.raises(CommandError) as exc:
        build_command(req(ports=spec), env(), catalog)
    assert exc.value.field == "options.ports"


def test_count_ports():
    assert count_ports("22,80,8000-8100") == 103
    assert count_ports("1-65535") == 65535


@pytest.mark.parametrize("opts", [{"timing": 6}, {"timing": "x"}, {"top_ports": 0}, {"version_intensity": 10}, {"host_timeout": "10x"}])
def test_out_of_range_values_rejected(catalog, opts):
    with pytest.raises(CommandError):
        build_command(req(**opts), env(), catalog)


def test_duration_accepted(catalog):
    assert "30m" in build_command(req(host_timeout="30m"), env(), catalog).argv


@pytest.mark.parametrize("target", ["-iL /etc/shadow", "; rm -rf /", "$(id)", "--script=vuln", "192.168.1.1;id", "-oN /etc/x"])
def test_injection_targets_rejected(catalog, target):
    with pytest.raises(CommandError) as exc:
        build_command(req(target=target), env(), catalog)
    assert exc.value.field == "target"


def test_targets_are_last(catalog):
    built = build_command(req(target="10.0.0.1 10.0.0.2", fast=None), env(), catalog)
    assert built.argv[-2:] == ["10.0.0.1", "10.0.0.2"]


def test_ipv6_target_adds_dash_6(catalog):
    built = build_command(req(target="::1", fast=None), env(), catalog)
    assert "-6" in built.argv
    assert built.argv.index("-6") < built.argv.index("::1")


def test_ipv4_target_has_no_dash_6(catalog):
    assert "-6" not in build_command(req(fast=None), env(), catalog).argv


def test_mixed_ip_families_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(target="192.168.1.1 ::1"), env(), catalog)
    assert exc.value.field == "target"


def test_duplicate_tokens_emitted_once(catalog):
    built = build_command(req(profile="everything", service_version=None), env(), catalog)
    assert built.argv.count("-sV") == 1
    assert built.argv.count("-O") == 1
    assert "--traceroute" in built.argv


def test_verbose_not_duplicated(catalog):
    built = build_command(req(verbose=None), env(), catalog)
    assert built.argv.count("-v") == 1


def test_parts_cover_argv_exactly(catalog):
    built = build_command(req(profile="services", target="192.168.1.0/24"), env(), catalog)
    assert " ".join(p.token for p in built.parts) == " ".join(built.argv[1:])
    kinds = [p.kind for p in built.parts]
    assert kinds[-1] == "target"
    assert "plumbing" in kinds and "option" in kinds
    assert all(p.text for p in built.parts)


def test_warning_for_huge_target(catalog):
    built = build_command(req(target="10.0.0.0/8", ping_only=None), env(), catalog)
    assert any("16,777,216" in w for w in built.warnings)


def test_warning_for_udp_all_ports(catalog):
    built = build_command(req(udp_scan=None, all_ports=None), env(), catalog)
    assert any("UDP" in w for w in built.warnings)


def test_no_udp_warning_for_top_20(catalog):
    built = build_command(req(profile="udp_common"), env(), catalog)
    assert not any("UDP" in w for w in built.warnings)


@pytest.mark.parametrize("level,word", [(5, "miss"), (0, "slow"), (1, "slow")])
def test_timing_warnings(catalog, level, word):
    built = build_command(req(timing=level), env(), catalog)
    assert any(word in w for w in built.warnings)


def test_version_intensity_without_sv_warns(catalog):
    built = build_command(req(version_intensity=9), env(), catalog)
    assert any("-sV" in w for w in built.warnings)


def test_missing_nmap_path_falls_back_to_name(catalog):
    e = Environment(is_root=True, can_raw=True, nmap_path=None, nmap_version=None, in_container=False)
    assert build_command(req(fast=None), e, catalog).argv[0] == "nmap"
