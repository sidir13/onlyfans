"""Tests du modèle physique thermique et des fonctions de bruit."""
from __future__ import annotations

import numpy as np
import pytest

from simulation.noise import (
    accumulate_drift,
    add_spike,
    exponential_event,
    gaussian_noise,
    uniform_event,
    weibull_event,
)
from simulation.physics import (
    compute_cost,
    compute_energy_kwh,
    compute_fan_auto_speed,
    compute_heat_input,
    compute_load_power,
    compute_tau,
    compute_thermal_step,
)


# ─── Paramètres de référence (rôle master) ───────────────────────────────────

IDLE_W = 200.0
MAX_W = 1700.0
HEAT_RATIO = 0.70
T_AMB = 22.0
C_TH = 800.0
TAU_MAX = 90.0
K_COOL = 3.5
ALPHA = 1.5
FAN_MAX = 5000
GAIN = 50.0
DT = 0.1  # 10 Hz


class TestComputeLoadPower:
    def test_zero_load_returns_idle(self):
        p = compute_load_power(0.0, IDLE_W, MAX_W, ALPHA)
        assert p == pytest.approx(IDLE_W)

    def test_full_load_returns_max(self):
        p = compute_load_power(1.0, IDLE_W, MAX_W, ALPHA)
        assert p == pytest.approx(MAX_W)

    def test_intermediate_load(self):
        p = compute_load_power(0.5, IDLE_W, MAX_W, ALPHA)
        expected = IDLE_W + (MAX_W - IDLE_W) * (0.5 ** ALPHA)
        assert p == pytest.approx(expected)

    def test_load_clamped_above_one(self):
        p_over = compute_load_power(1.5, IDLE_W, MAX_W, ALPHA)
        p_one = compute_load_power(1.0, IDLE_W, MAX_W, ALPHA)
        assert p_over == pytest.approx(p_one)

    def test_load_clamped_below_zero(self):
        p_neg = compute_load_power(-0.5, IDLE_W, MAX_W, ALPHA)
        p_zero = compute_load_power(0.0, IDLE_W, MAX_W, ALPHA)
        assert p_neg == pytest.approx(p_zero)


class TestComputeHeatInput:
    def test_heat_input_is_fraction_of_power(self):
        q = compute_heat_input(1000.0, HEAT_RATIO)
        assert q == pytest.approx(700.0)

    def test_zero_power_zero_heat(self):
        assert compute_heat_input(0.0, HEAT_RATIO) == pytest.approx(0.0)


class TestComputeTau:
    def test_tau_max_when_fans_stopped(self):
        tau = compute_tau(TAU_MAX, fan_rpm_mean=0.0, k_cool=K_COOL)
        assert tau == pytest.approx(TAU_MAX)

    def test_tau_decreases_with_fan_speed(self):
        tau_slow = compute_tau(TAU_MAX, fan_rpm_mean=1000.0, k_cool=K_COOL)
        tau_fast = compute_tau(TAU_MAX, fan_rpm_mean=4000.0, k_cool=K_COOL)
        assert tau_fast < tau_slow < TAU_MAX

    def test_tau_positive(self):
        tau = compute_tau(TAU_MAX, fan_rpm_mean=5000.0, k_cool=K_COOL)
        assert tau > 0


class TestComputeThermalStep:
    def test_temperature_increases_under_load_no_fans(self):
        """Sans fans et sous forte charge, la température doit monter."""
        T = T_AMB
        q_in = compute_heat_input(
            compute_load_power(0.8, IDLE_W, MAX_W, ALPHA), HEAT_RATIO
        )
        tau = compute_tau(TAU_MAX, fan_rpm_mean=0.0, k_cool=K_COOL)
        for _ in range(100):
            T = compute_thermal_step(T, q_in, tau, C_TH, T_AMB, DT)
        assert T > 40.0, f"Température trop basse : {T:.1f}°C"

    def test_temperature_stabilizes_with_fans(self):
        """Avec des fans rapides, la température doit se stabiliser."""
        T = 80.0
        q_in = compute_heat_input(
            compute_load_power(0.5, IDLE_W, MAX_W, ALPHA), HEAT_RATIO
        )
        tau = compute_tau(TAU_MAX, fan_rpm_mean=4000.0, k_cool=K_COOL)
        for _ in range(500):
            T = compute_thermal_step(T, q_in, tau, C_TH, T_AMB, DT)
        assert T < 75.0, f"Température trop élevée avec fans : {T:.1f}°C"

    def test_temperature_approaches_ambient_without_load(self):
        """Sans charge, la température doit converger vers T_amb."""
        T = 80.0
        q_in = 0.0
        tau = compute_tau(TAU_MAX, fan_rpm_mean=0.0, k_cool=K_COOL)
        for _ in range(3000):
            T = compute_thermal_step(T, q_in, tau, C_TH, T_AMB, DT)
        assert abs(T - T_AMB) < 5.0, f"T={T:.1f}°C ne converge pas vers T_amb={T_AMB}°C"

    def test_dt_zero_no_change(self):
        T = 50.0
        q_in = 500.0
        tau = compute_tau(TAU_MAX, 0.0, K_COOL)
        T_new = compute_thermal_step(T, q_in, tau, C_TH, T_AMB, dt=0.0)
        assert T_new == pytest.approx(T)


class TestComputeFanAutoSpeed:
    def test_at_ambient_temp_fans_stopped(self):
        rpm = compute_fan_auto_speed(T_AMB, T_AMB, GAIN, FAN_MAX)
        assert rpm == 0

    def test_above_ambient_fans_proportional(self):
        rpm = compute_fan_auto_speed(T_AMB + 20.0, T_AMB, GAIN, FAN_MAX)
        assert rpm == int(GAIN * 20.0)

    def test_fans_clamped_to_max(self):
        rpm = compute_fan_auto_speed(T_AMB + 10000.0, T_AMB, GAIN, FAN_MAX)
        assert rpm == FAN_MAX

    def test_below_ambient_fans_stopped(self):
        rpm = compute_fan_auto_speed(T_AMB - 5.0, T_AMB, GAIN, FAN_MAX)
        assert rpm == 0


class TestComputeEnergyKwh:
    def test_energy_is_positive(self):
        e = compute_energy_kwh(1000.0, 2, 15.0, 10.0)
        assert e > 0

    def test_energy_grows_with_power(self):
        e1 = compute_energy_kwh(500.0, 2, 15.0, 10.0)
        e2 = compute_energy_kwh(1000.0, 2, 15.0, 10.0)
        assert e2 > e1

    def test_energy_cumulates_over_ticks(self):
        """L'énergie cumulée croît strictement à chaque tick."""
        cumulated = 0.0
        prev = -1.0
        for _ in range(100):
            cumulated += compute_energy_kwh(1000.0, 2, 15.0, 10.0)
            assert cumulated > prev
            prev = cumulated

    def test_fans_contribute_to_energy(self):
        e_no_fans = compute_energy_kwh(1000.0, 0, 15.0, 10.0)
        e_with_fans = compute_energy_kwh(1000.0, 2, 15.0, 10.0)
        assert e_with_fans > e_no_fans


class TestComputeCost:
    def test_cost_proportional_to_energy(self):
        c1 = compute_cost(1.0, 1.4, 0.20)
        c2 = compute_cost(2.0, 1.4, 0.20)
        assert c2 == pytest.approx(2 * c1)

    def test_pue_above_one_increases_cost(self):
        c_no_pue = compute_cost(1.0, 1.0, 0.20)
        c_with_pue = compute_cost(1.0, 1.4, 0.20)
        assert c_with_pue > c_no_pue


class TestGaussianNoise:
    def test_zero_std_returns_value(self):
        assert gaussian_noise(50.0, 0.0) == pytest.approx(50.0)

    def test_output_close_to_value(self):
        """Sur 1000 tirages, la moyenne doit être proche de la valeur."""
        samples = [gaussian_noise(50.0, 0.3) for _ in range(1000)]
        assert abs(np.mean(samples) - 50.0) < 0.1

    def test_no_extreme_outliers(self):
        """Aucune valeur ne doit dépasser ±5σ (probabilité < 3e-7)."""
        std = 0.3
        samples = [gaussian_noise(50.0, std) for _ in range(10000)]
        assert all(abs(s - 50.0) < 5 * std for s in samples)


class TestAddSpike:
    def test_zero_probability_no_spike(self):
        for _ in range(100):
            assert add_spike(50.0, 0.0, 10.0) == pytest.approx(50.0)

    def test_probability_one_always_spikes(self):
        for _ in range(20):
            assert add_spike(50.0, 1.0, 5.0) == pytest.approx(55.0)

    def test_spike_adds_magnitude(self):
        result = add_spike(50.0, 1.0, 3.0)
        assert result == pytest.approx(53.0)


class TestAccumulateDrift:
    def test_drift_increases_over_time(self):
        drift = 0.0
        for _ in range(10):
            drift = accumulate_drift(drift, rate_per_s=0.01, dt=1.0)
        assert drift == pytest.approx(0.10)

    def test_zero_rate_no_drift(self):
        drift = accumulate_drift(5.0, rate_per_s=0.0, dt=1.0)
        assert drift == pytest.approx(5.0)


class TestWeibullEvent:
    def test_elapsed_zero_no_event(self):
        assert weibull_event(1.5, 7200, elapsed_s=0, dt=0.1) is False

    def test_high_elapsed_high_probability(self):
        """Avec β>1 et t >> η, la probabilité doit être élevée sur dt grand."""
        # t=10×scale, dt=100s → très haute probabilité
        result = weibull_event(shape=2.0, scale_s=100.0, elapsed_s=1000.0, dt=100.0)
        # On ne peut pas garantir True sur un seul tirage,
        # mais la probabilité doit être ~1
        # On le vérifie statistiquement
        count = sum(
            weibull_event(2.0, 100.0, 1000.0, 100.0)
            for _ in range(20)
        )
        assert count >= 15, f"Seulement {count}/20 événements (attendu ~20)"


class TestExponentialEvent:
    def test_large_dt_high_probability(self):
        """Avec dt >> scale_s, la probabilité tend vers 1."""
        count = sum(exponential_event(1.0, 100.0) for _ in range(20))
        assert count >= 18

    def test_zero_scale_no_event(self):
        assert exponential_event(0.0, 0.1) is False


class TestUniformEvent:
    def test_zero_probability_no_event(self):
        for _ in range(100):
            assert uniform_event(0.0) is False

    def test_one_probability_always_event(self):
        for _ in range(20):
            assert uniform_event(1.0) is True
