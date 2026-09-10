from spo_pool_heat_pump.drivers.base import HeatPumpState
from spo_pool_heat_pump.drivers.decode import apply_map
from spo_pool_heat_pump.profiles import decode_faults, fault_meanings, fault_source, load_profile, profile_registers


def test_e03_verified_from_dump() -> None:
    profile = load_profile("mida_cosma_pc1002")
    spec = profile_registers(profile)["faults"]
    codes = decode_faults({2074: 1 << 9, 2075: 0, 2076: 0, 2077: 0}, spec)
    assert codes == ["E03"]
    assert fault_meanings(codes, spec) == ["Flow switch — no water"]
    assert fault_source("E03", spec) == "verified"
    state = apply_map(profile, {2074: 1 << 9})
    assert state.fault_code == "E03"
    assert state.fault_text == "Flow switch — no water"
    assert state.card_status() == "Fault · E03"


def test_community_p01() -> None:
    profile = load_profile("mida_cosma_pc1002")
    spec = profile_registers(profile)["faults"]
    codes = decode_faults({2074: 1 << 0}, spec)
    assert codes == ["P01"]
    assert fault_meanings(codes, spec) == ["Inlet temperature sensor"]
    assert fault_source("P01", spec) == "community"


def test_unmapped_bit_stays_raw() -> None:
    profile = load_profile("mida_cosma_pc1002")
    spec = profile_registers(profile)["faults"]
    codes = decode_faults({2074: 1 << 15}, spec)
    assert codes == ["2074.15"]
    assert fault_meanings(codes, spec) == [""]
    state = apply_map(profile, {2074: 1 << 15})
    assert state.fault_code == "2074.15"
    assert state.fault_text is None


def test_community_and_verified_together() -> None:
    profile = load_profile("mida_cosma_pc1002")
    spec = profile_registers(profile)["faults"]
    codes = decode_faults({2074: (1 << 0) | (1 << 9)}, spec)
    assert codes == ["P01", "E03"]
    assert fault_meanings(codes, spec)[1] == "Flow switch — no water"


def test_fault_text_joins_known_only() -> None:
    state = HeatPumpState(faults=["E03", "E01"], fault_texts=["Flow switch — no water", "High pressure protection"])
    assert state.fault_text == "Flow switch — no water · High pressure protection"


def test_oem_booklet_lists_unmapped() -> None:
    spec = profile_registers(load_profile("mida_cosma_pc1002"))["faults"]
    booklet = spec["booklet"]
    assert booklet["P15"]["bit"] is None
    assert booklet["P09"]["bit"] is None
    assert booklet["E05"]["bit"] is None
    assert booklet["E08"]["bit"] is None
    assert booklet["E081"]["bit"] is None
    assert booklet["TP"]["bit"] is None
    assert booklet["F05"]["bit"] is None
    assert booklet["F06"]["bit"] is None
    assert booklet["P01"]["bit"] == "2074.0"
    assert booklet["E03"]["bit"] == "2074.9"
    assert "P15" not in spec["codes"].values()
    assert spec["aliases"]["F51"] == "F051"
    assert spec["meanings"]["P15"] == "Coil 2 temperature sensor"
    assert spec["meanings"]["E08"] == "Display communication fault"
    assert fault_meanings(["F51"], spec) == ["EC fan feedback fault"]
    missing = [code for code, row in booklet.items() if row.get("bit") is None]
    assert missing == ["P15", "P082", "P09", "E05", "E08", "E081", "TP", "F05", "F06", "F09", "F10", "F11", "F23"]


def test_every_community_bit_has_source() -> None:
    spec = profile_registers(load_profile("mida_cosma_pc1002"))["faults"]
    bits = spec["bits"]
    assert spec["sources"]["E03"] == "verified"
    assert bits["2074.9"]["observed"]
    for key, val in bits.items():
        assert val["source"] in ("verified", "community")
        assert val["code"]
        assert val["text"]
        assert "." in key
