# Roadmap — Juste des ventilateurs

> Projet `juste-ventilateurs` branché sur le simulateur `jumeaux-chauds`.  
> ✅ = fait | ☐ = à faire

---

## Phase 1 — Prise en main ✅

- [x] Lancer `jumeaux-chauds` avec le scénario `stress`
- [x] Explorer la télémétrie MQTT (topics, payloads, structure)
- [x] Identifier les endpoints REST de contrôle des ventilateurs (`fan_mode`, `fan_speed`)
- [x] Comprendre les états (`on`, `degraded`, `off`) et la logique d'arrêt thermique automatique

---

## Phase 2 — Ingestion & stockage

- [x] Subscriber MQTT fiable (`consumer/mqtt_to_timescale.py`)
- [x] Schéma TimescaleDB : tables `telemetry` + `events`, vue agrégée `telemetry_1min`
- [x] Parsing/normalisation des payloads (cluster, machine, ts, temp, RPM, power, load)
- [x] Export Parquet/CSV versionné par épisode + seed → dataset reproductible (`ingest/mqtt_recorder.py`)
- [x] Splits train / validation / test par épisode (`ingest/export_dataset.py`)

---

## Phase 3 — Feature engineering

- [x] Features temps réel : `dT_5s`, `dT_15s`, `dT_30s`, marge au shutdown, rolling mean RPM (`features/engineer.py`)
- [x] Features contextuelles : `time_in_hot_zone_s`, `recent_degraded_30s/60s`, `fan_changes_30s/60s`
- [x] Features énergie : `cost_eur` (énergie × PUE × prix), `power_w_mean_15s`

---

## Phase 4 — Modèle d'anticipation de pannes ✅

- [x] Définir les labels : `failure_60s` (degraded/off dans 60 s), `hot_30s` (T > seuil) → `models/labels.py`
- [x] Baseline heuristique (seuils fixes, règle si T > T_warn depuis N secondes) → `models/baseline.py`
- [x] Modèle supervisé : Random Forest ou GBM (XGBoost/LightGBM) → `models/train.py`
- [x] Évaluation : Precision, Recall, F1, PR-AUC + **temps moyen d'anticipation** → `models/evaluate.py`
- [x] Validation par épisodes, analyse des faux négatifs → `models/evaluate.py::evaluate_by_episode`

---

## Phase 5 — Contrôleur de régulation des ventilateurs

- [ ] Baselines : RPM fixe, contrôle à seuils, PID simple
- [ ] Actions discrètes : RPM ∈ {0, 1500, 2500, 3500, 4500}
- [ ] Politique : classifieur supervisé ou score multi-objectif  
      `J(t) = α·risk(t) + β·heat(t) + γ·energy(t) + δ·|ΔRPMt|`
- [ ] *(Optionnel avancé)* Contextual bandit ou RL léger

---

## Phase 6 — Boucle fermée & évaluation

- [ ] Passer les machines en `manual` via API, brancher le contrôleur en temps réel
- [ ] Logger toutes les décisions et résultats observés
- [ ] Comparer sur même scénario : native auto vs PID vs modèle ML
- [ ] Tests de robustesse : bruit capteur, charge variable, drift rapide, pannes fréquentes

---

## Livrables finaux

- [ ] Dépôt `juste-ventilateurs` dockerisé + README complet
- [ ] Dataset versionné en Parquet (train/val/test) avec description du schéma
- [ ] Modèles sauvegardés (joblib / ONNX)
- [ ] Rapport : matrices de confusion, courbes PR/ROC, métriques shutdown/énergie vs baselines

---

## Ce qui peut être implémenté maintenant

Avec le simulateur opérationnel (MQTT, API REST, TimescaleDB, consumer), tout jusqu'à la **Phase 5** peut être codé :  
les phases 2→5 sont des tâches de développement pur (scripts, notebooks, modèles).  
La **Phase 6** nécessite du temps de run en live pour collecter des données et valider en boucle fermée.
