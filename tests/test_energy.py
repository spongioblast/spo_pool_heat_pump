from spo_pool_heat_pump.energy import EnergyIntegrator


def test_trapezoid() -> None:
    integ = EnergyIntegrator()
    integ.update(2.0, 0.0)
    # 2 kW for 1800 s = 1 kWh if constant; trapezoid of 2→2 is 1 kWh
    total = integ.update(2.0, 1800.0)
    assert abs(total - 1.0) < 1e-6


def test_ignores_huge_gap() -> None:
    integ = EnergyIntegrator()
    integ.update(2.0, 0.0)
    total = integ.update(2.0, 10_000.0)
    assert total == 0.0
