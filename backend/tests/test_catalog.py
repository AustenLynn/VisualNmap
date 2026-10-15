import shutil
from pathlib import Path

import pytest

from visualnmap.catalog import CatalogError, load_catalog

CATALOG_DIR = Path(__file__).resolve().parents[1] / "visualnmap" / "catalog"


def test_every_option_has_full_explanation(catalog):
    assert len(catalog.options) >= 28
    for opt in catalog.options.values():
        for field in ("label", "summary", "details", "when_to_use", "example"):
            assert getattr(opt, field).strip(), f"{opt.id} missing {field}"


def test_option_with_value_renders_with_value(catalog):
    for opt in catalog.options.values():
        if opt.render in ("separate", "attached"):
            assert opt.value is not None, opt.id
        else:
            assert opt.value is None, opt.id


def test_conflicts_reference_known_options(catalog):
    for opt in catalog.options.values():
        for other in opt.conflicts_with:
            assert other in catalog.options, f"{opt.id} conflicts with unknown {other}"


def test_groups_cover_all_options(catalog):
    group_ids = {g.id for g in catalog.groups}
    assert {o.group for o in catalog.options.values()} <= group_ids


def test_profiles_reference_known_options_and_compute_root(catalog):
    assert set(catalog.profiles) == {
        "find_devices", "quick_ports", "full_ports", "services",
        "os_detect", "stealth", "udp_common", "everything",
    }
    for profile in catalog.profiles.values():
        for po in profile.options:
            assert po.id in catalog.options
    assert catalog.profiles["quick_ports"].requires_root is False
    assert catalog.profiles["stealth"].requires_root is True
    assert catalog.profiles["everything"].requires_root is True


def test_ports_and_states(catalog):
    assert len(catalog.ports) >= 55
    assert all(1 <= p <= 65535 for p in catalog.ports)
    assert catalog.ports[22].service == "ssh"
    assert set(catalog.states) == {"open", "closed", "filtered", "unfiltered", "open|filtered", "closed|filtered"}


def _copy_catalog(tmp_path: Path) -> Path:
    dest = tmp_path / "catalog"
    dest.mkdir()
    for name in ("options.yaml", "profiles.yaml", "ports.yaml"):
        shutil.copy(CATALOG_DIR / name, dest / name)
    return dest


def test_unknown_profile_option_is_rejected(tmp_path):
    d = _copy_catalog(tmp_path)
    text = (d / "profiles.yaml").read_text().replace("{ id: ping_only }", "{ id: does_not_exist }")
    (d / "profiles.yaml").write_text(text)
    with pytest.raises(CatalogError, match="does_not_exist"):
        load_catalog(d)


def test_duplicate_option_id_is_rejected(tmp_path):
    d = _copy_catalog(tmp_path)
    text = (d / "options.yaml").read_text().replace("- id: fast\n", "- id: ports\n")
    (d / "options.yaml").write_text(text)
    with pytest.raises(CatalogError, match="duplicate"):
        load_catalog(d)
