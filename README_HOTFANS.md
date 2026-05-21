# README — Pipeline complète `juste-ventilateurs`

Ce guide décrit chaque commande à exécuter dans l'ordre pour aller de zéro jusqu'au modèle entraîné.  
**Mets à jour ce fichier** (case `[x]`) au fil de tes actions.

---

## Prérequis

- Docker Desktop lancé
- Python ≥ 3.10
- Le virtualenv `hotfans` (déjà créé dans ce repo)

---

## Étape 0 — Activer le virtualenv

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\hotfans\Scripts\Activate.ps1
```

- [ ] virtualenv activé (le prompt affiche `(hotfans)`)

---

## Étape 1 — Installer les dépendances

### 1a. Dépendances du simulateur (API, MQTT, dashboard)

```powershell
pip install -r requirements.txt
pip install -r requirements.dashboard.txt
```

### 1b. Dépendances du package ML `juste-ventilateurs`

```powershell
cd juste-ventilateurs
pip install -e .
pip install scikit-learn lightgbm joblib matplotlib
cd ..
```

- [ ] `pip install` terminé sans erreur

---

## Étape 2 — Démarrer l'infrastructure

### Option A — Avec Docker (recommandé)

Uvicorn tourne **à l'intérieur** du conteneur `iot-twin` : pas besoin de le lancer à la main.

```powershell
# Mode minimal : simulateur + dashboard (sans base de données)
docker compose up -d

# Mode complet : + TimescaleDB + consumer + Grafana
docker compose --profile storage up -d
```

Services lancés :
| Service | URL |
|---|---|
| Simulateur + API REST | http://localhost:8000 |
| Dashboard Streamlit | http://localhost:8501 |
| Broker MQTT | `localhost:1883` |
| TimescaleDB (profil storage) | `localhost:5432` |
| Grafana (profil storage) | http://localhost:3000 (admin / admin) |

- [ ] `docker compose ps` montre tous les services `healthy`

### Option B — Sans Docker (développement local)

Il faut démarrer chaque service manuellement dans des terminaux séparés.

**Terminal 1 — Broker MQTT** (Docker suffit juste pour mosquitto) :
```powershell
docker compose up -d mosquitto
```

**Terminal 2 — API FastAPI + simulateur** :
```powershell
$env:MQTT_BROKER_HOST = "localhost"
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3 — Dashboard Streamlit** (optionnel) :
```powershell
streamlit run dashboard/app.py
```

- [ ] `http://localhost:8000/` répond
- [ ] `http://localhost:8501/` répond (si dashboard lancé)

---

## Étape 3 — Vérifier que le simulateur tourne

```powershell
curl http://localhost:8000/
curl http://localhost:8000/cluster
```

Pour changer de scénario (ex. `stress`) :

```powershell
$env:SCENARIO = "stress"
docker compose up -d iot-twin
```

- [ ] L'API répond, le cluster est visible

---

## Étape 4 — Enregistrer la télémétrie (Phase 2)

Enregistre 5 minutes de télémétrie MQTT dans un fichier Parquet brut.

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.ingest.mqtt_recorder `
    --duration 300 `
    --output data/raw `
    --seed 42
cd ..
```

Fichier produit : `juste-ventilateurs/data/raw/telemetry_<ts>_seed42.parquet`

- [ ] Fichier Parquet présent dans `data/raw/`

---

## Étape 5 — Exporter depuis TimescaleDB (Phase 2, optionnel)

> Uniquement si tu as lancé le profil `storage` à l'étape 2.

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.ingest.export_dataset `
    --split 0.70 0.15 0.15 `
    --output data/splits
cd ..
```

Fichiers produits : `data/splits/train.parquet`, `val.parquet`, `test.parquet`

- [ ] Splits créés dans `data/splits/`

---

## Étape 6 — Feature engineering (Phase 3)

Enrichit le Parquet brut avec toutes les features ML (dérivées de température,
rolling RPM, coût énergie, etc.).

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.features.engineer `
    data/raw/<ton_fichier>.parquet `
    --output data/features/ep01.parquet
cd ..
```

> Remplace `<ton_fichier>` par le nom réel du fichier créé à l'étape 4.

Fichier produit : `data/features/ep01.parquet`

- [ ] Features calculées, fichier présent dans `data/features/`

---

## Étape 7 — Générer les labels (Phase 4)

Crée les colonnes `failure_60s` et `hot_30s` (prédiction prospective de panne).

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.models.labels `
    data/features/ep01.parquet `
    --output data/labeled/ep01.parquet
cd ..
```

Fichier produit : `data/labeled/ep01.parquet`

- [ ] Labels générés, les taux de positifs sont affichés dans les logs

---

## Étape 8 — Entraîner le modèle (Phase 4)

### Avec LightGBM (recommandé)

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.models.train `
    data/labeled/ep01.parquet `
    --target failure_60s `
    --model lgbm `
    --output models/failure_lgbm.joblib
cd ..
```

### Avec Random Forest

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.models.train `
    data/labeled/ep01.parquet `
    --target failure_60s `
    --model rf `
    --output models/failure_rf.joblib
cd ..
```

Fichiers produits : `models/failure_lgbm.joblib` + `models/failure_lgbm.meta.json`

- [ ] Modèle sauvegardé, métriques de validation affichées dans les logs

---

## Étape 9 — Évaluer le modèle (Phase 4)

```powershell
cd juste-ventilateurs
python -m juste_ventilateurs.models.evaluate `
    models/failure_lgbm.joblib `
    data/labeled/ep01.parquet `
    --target failure_60s `
    --plot `
    --output-dir reports
cd ..
```

Fichiers produits :
- `reports/failure_60s_report.json` — métriques JSON (Precision, Recall, F1, PR-AUC, lead time)
- `reports/failure_60s_curves.png` — courbes Précision-Rappel, ROC, matrice de confusion

- [ ] Rapport JSON créé
- [ ] Courbes générées dans `reports/`

---

## Étape 10 — Arrêter les services Docker

```powershell
docker compose down
# ou avec le profil storage :
docker compose --profile storage down
```

- [ ] Tous les conteneurs arrêtés

---

## Récapitulatif des commandes rapides (Makefile)

```powershell
make docker-up        # démarre simulateur + dashboard
make docker-storage   # démarre tout (avec TimescaleDB + Grafana)
make docker-down      # arrête tout
make test             # lance les tests unitaires
make lint             # vérifie le style de code
```

---

## Ordre de dépendance des étapes

```
0 (venv) → 1 (install) → 2 (docker) → 3 (vérif API)
                                     ↓
                              4 (enregistrer)  ←→  5 (export DB, optionnel)
                                     ↓
                              6 (features)
                                     ↓
                              7 (labels)
                                     ↓
                              8 (train)
                                     ↓
                              9 (evaluate)
```
