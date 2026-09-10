from pathlib import Path

CARD = Path(__file__).resolve().parents[1] / "custom_components/spo_pool_heat_pump/www/spo-pool-heat-pump-card.js"
ICON = Path(__file__).resolve().parents[1] / "custom_components/spo_pool_heat_pump/brand/icon.png"
WWW = Path(__file__).resolve().parents[1] / "custom_components/spo_pool_heat_pump/www"
DOCS_WIRING = Path(__file__).resolve().parents[1] / "docs/images/dr164-parallel-tap.png"


def test_card_bundle_committed() -> None:
    text = CARD.read_text(encoding="utf-8")
    assert "spo-pool-heat-pump-card" in text
    assert "spo-pool-heat-pump-settings-card" in text
    assert "spo-pool-heat-pump-parameters-card" not in text
    assert "SPO Pool Heat Pump" in text
    assert "schematic" in text
    assert "animationEnabled" in text or "animation" in text
    assert "flow_animation" in text
    assert 'data-flow="false"' in text or "data-flow" in text
    assert "fanwrap" in text
    assert "circuit" in text
    assert "section" in text
    assert "static properties" in text or "staticProperties" in text or ".properties =" in text
    assert "attribute" in text
    assert "--warm:" in text
    assert ".w3 .eyebrow" in text
    assert "fault-why" in text
    assert "spo-pool-heat-pump-card-editor" in text
    assert "ha-switch" in text
    assert "ha-dialog" in text
    assert "bubbles: true" in text
    assert "composed: true" in text
    assert "min_temp" in text
    assert "device_id" in text
    assert 'id="basin19"' not in text
    assert "openMoreInfo" in text
    assert "spo_pool_heat_pump/parameters/list" in text
    assert "spo_pool_heat_pump/parameters/set" in text
    assert "spo_pool_heat_pump/parameters/refresh" in text
    assert "spo_pool_heat_pump/dump/start" in text
    assert "spo_pool_heat_pump/dump/status" in text
    assert "Bus dump" in text
    assert "dumpOnly" in text or "dump_only" in text
    assert "Use Settings" in text
    assert "What is a bus dump?" in text
    assert "Start the capture first" in text
    assert "Screenshot the phone app" in text
    assert "Settings" in text
    assert "Heat pump settings" in text
    assert "COP " in text
    assert "copMark" in text or "COP ${" in text or ">COP " in text
    assert "unsafeHTML" not in text
    assert "shouldUpdate" in text
    assert "_targetLocal" in text
    assert "service_menu_writes" in text
    assert "Enable changing service settings in the integration options first" in text
    assert "can brick the unit" in text
    assert "installer_writes" not in text
    assert "this._config = {}" in text
    assert "this._params =" in text
    assert "getGridOptions" in text
    assert "customElements.get" in text
    assert "Administrator only" in text
    assert "is_admin === true" in text or "is_admin===true" in text
    assert "applyView" not in text
    assert "\n  hass;\n" not in text
    assert "\n  _config = {};\n" not in text
    assert "\n  _params = emptyParametersView();\n" not in text


def test_brand_icon() -> None:
    assert ICON.exists()
    assert ICON.stat().st_size > 100
    assert ICON.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_setup_guide_and_wiring_diagram() -> None:
    html = (WWW / "setup.html").read_text(encoding="utf-8")
    assert "USR-DR164" in html
    assert "10.10.100.254" in html
    assert "8899" in html
    assert "Modbus" in html
    assert "docs/images/dr164-parallel-tap.png" in html
    assert "<img" not in html
    assert DOCS_WIRING.exists()
    assert DOCS_WIRING.stat().st_size > 100
    assert DOCS_WIRING.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_www_has_no_dump_files() -> None:
    assert not list(WWW.glob("*.log"))
    assert not list(WWW.glob("*.bin"))
    assert not list(WWW.glob("*dump*.png"))


def test_wiring_diagram_has_a_single_copy() -> None:
    repo = DOCS_WIRING.parents[2]
    copies = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("dr164-parallel-tap.png"))
    assert copies == ["docs/images/dr164-parallel-tap.png"]
