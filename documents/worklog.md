# Jumeaux Chauds — Journal de développement

> **Auteur :** Tristan Vanrullen  
> **Démarrage :** Mai 2026

Ce fichier trace chronologiquement les développements réalisés, les décisions techniques prises et les écarts éventuels par rapport aux spécifications initiales.

---

## 2026-05-18 — Phase 1 : Fondations

### Étape 1.1 — Bootstrap du projet ✅

**Fichiers créés :**
- `requirements.txt` — dépendances simulateur + API (versions figées)
- `requirements.dashboard.txt` — dépendances dashboard Streamlit
- `requirements.consumer.txt` — dépendances consumer TimescaleDB
- `requirements.test.txt` — dépendances de test (ajout de `pytest-cov`)
- `pyproject.toml` — configuration ruff, mypy, pytest
- `Makefile` — commandes : `install`, `install-all`, `dev`, `test`, `test-cov`, `docker-up`, `docker-down`, `docker-storage`, `lint`, `format`
- Squelettes `__init__.py` pour tous les packages : `simulation/`, `mqtt/`, `api/`, `api/routes/`, `consumer/`, `dashboard/`, `dashboard/components/`, `tests/`
- Squelettes vides pour tous les modules futurs (commentaire indiquant la phase d'implémentation)
- `mosquitto/config/mosquitto.conf` — configuration broker dev (allow_anonymous, TCP 1883 + WS 9001)
- `grafana/provisioning/.gitkeep` — répertoire versionnable

**Notes :**
- `pytest-cov==5.0.0` ajouté à `requirements.test.txt` (non mentionné dans les specs initiales mais nécessaire pour `make test-cov`)
- Les squelettes permettent d'importer tous les packages sans erreur dès maintenant

---

### Étape 1.2 — Système de configuration YAML (OmegaConf) ✅

**Fichiers créés :**
- `config/__init__.py`
- `config/base.yaml` — configuration complète du cluster (rôles master/worker, 5 machines, MQTT, paramètres thermiques)
- `config/scenarios/nominal.yaml` — profil sine_wave, pas de pannes
- `config/scenarios/stress.yaml` — profil ramp_with_spikes, pannes Weibull/exponentielle/uniforme
- `config/loader.py` — `load_config()` avec merge 3 niveaux + surcharges ENV, `get_machine_config()` avec héritage rôle → machine
- `simulation/duration.py` — `parse_duration()` supportant `"0"`, `"30s"`, `"5m"`, `"1h30m"`, `"2h15m30s"`, nombres purs
- `tests/conftest.py` — fixtures `fix_random_seed` (autouse), `nominal_config`, `stress_config`, `master_thermal_params`
- `tests/test_config.py` — 14 tests couvrant : chargement nominal/stress, merge, surcharges programmatiques, surcharge individuelle `srv-master-02`, erreurs

**Décisions techniques :**
- `get_machine_config()` utilise `OmegaConf.masked_copy()` pour extraire les surcharges individuelles sans inclure `id` et `role`
- La surcharge ENV (`CLUSTER_ID`, `MQTT_BROKER_HOST`, `TICK_RATE_HZ`) est appliquée après le merge YAML
- `parse_duration("0")` et `parse_duration("")` retournent `0.0` (durée infinie)

---

### Étape 1.3 — Modèle physique (fonctions pures) ✅

**Fichiers créés :**
- `simulation/physics.py` — 7 fonctions pures : `compute_load_power`, `compute_heat_input`, `compute_tau`, `compute_thermal_step`, `compute_fan_auto_speed`, `compute_energy_kwh`, `compute_cost`
- `simulation/noise.py` — 6 fonctions : `gaussian_noise`, `add_spike`, `accumulate_drift`, `weibull_event`, `exponential_event`, `uniform_event`
- `tests/test_physics.py` — 35 tests couvrant toutes les fonctions physiques et de bruit

**Décisions techniques :**
- `weibull_event()` implémenté via le taux de défaillance instantané h(t) = (β/η)(t/η)^(β-1), approche standard en fiabilité industrielle
- `exponential_event()` : P = 1 - exp(-dt/scale_s), processus de Poisson homogène
- `uniform_event()` ajouté (non dans les specs initiales) pour supporter le type `power_surge` du scénario stress
- Toutes les fonctions sont purement déterministes quand numpy seed est fixé

---

## Prochaine étape

**Phase 2 — Étape 2.1 : MachineSimulator**
- Implémenter `simulation/machine.py` avec états ON/OFF/DEGRADED
- Implémenter la logique de tick, `inject_fault()`, `snapshot()`
- Écrire `tests/test_machine.py`
