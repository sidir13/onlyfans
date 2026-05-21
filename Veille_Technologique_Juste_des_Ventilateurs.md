# Veille Technologique — Juste des Ventilateurs
**Projet M2 Data-IA 2026 — Analyse de données temps réel IoT pour la supervision thermique de datacenters**

---

## Introduction

Ce document de veille technologique couvre l'ensemble des technologies, protocoles, outils et concepts mobilisés dans le cadre du projet "Juste des ventilateurs". L'objectif est de comprendre l'état de l'art des solutions disponibles dans quatre grandes catégories : l'IoT et la communication temps réel, le stockage et la gestion de données de séries temporelles, le machine learning appliqué à la prédiction de pannes et au contrôle, et enfin le déploiement et l'observabilité.

---

## 1. IoT et Communication Temps Réel

### 1.1 Le protocole MQTT

**MQTT** (Message Queuing Telemetry Transport) est un protocole de messagerie publish/subscribe léger, conçu pour les environnements à contraintes réseau (faible bande passante, latence variable). Il a été normalisé par l'OASIS et opère sur TCP/IP.

**Concepts fondamentaux :**
- **Broker** : serveur central qui reçoit et redistribue les messages (ex. Mosquitto, HiveMQ, EMQX).
- **Topics** : canaux de publication hiérarchiques (ex. `datacenter/cluster1/machine3/temperature`).
- **QoS (Quality of Service)** : trois niveaux garantissant la délivrance des messages (QoS 0 : au plus une fois, QoS 1 : au moins une fois, QoS 2 : exactement une fois).
- **Retain** : possibilité de conserver le dernier message d'un topic pour les nouveaux abonnés.

**Avantages pour l'IoT datacenter :**
- Très faible overhead (en-tête de 2 octets minimum).
- Adapté aux milliers de capteurs en publication simultanée.
- Supporte TLS pour la sécurisation des échanges.

**Mosquitto** est le broker MQTT open source de référence (projet Eclipse Foundation). Il est léger, simple à déployer et parfaitement adapté à un environnement de développement ou de production à moyenne échelle.

**Librairie Python :** `paho-mqtt` — la bibliothèque officielle Eclipse pour publier et s'abonner à des topics MQTT en Python.

### 1.2 Apache Kafka

**Apache Kafka** est une plateforme de streaming distribué orientée haute disponibilité et fort débit. Contrairement à MQTT, Kafka est conçu pour des volumes massifs de données avec persistance et replay possible.

**Concepts clés :**
- **Topics / Partitions** : données distribuées sur plusieurs brokers pour le parallélisme.
- **Consumer Groups** : plusieurs consommateurs en parallèle sur le même topic.
- **Log compaction** : conservation durable des événements avec capacité de rejeu.
- **Kafka Streams / ksqlDB** : traitement en flux directement dans Kafka.

**Comparaison MQTT vs Kafka :**

| Critère | MQTT | Kafka |
|---|---|---|
| Débit | Moyen | Très élevé |
| Latence | Très faible | Faible à moyen |
| Persistance | Non (par défaut) | Oui (configurable) |
| Replay | Non | Oui |
| Complexité | Faible | Élevée |
| Usage cible | IoT, capteurs | Big Data, microservices |

Dans le contexte du projet, MQTT est le protocole naturel du simulateur `jumeaux-chauds`. Kafka pourrait être envisagé si le volume de données ou les besoins de rejeu l'exigent.

### 1.3 Jumeaux numériques (Digital Twins)

Le concept de **jumeau numérique** (Digital Twin) désigne une réplique virtuelle d'un système physique, alimentée en temps réel par des données de capteurs et capable de simuler le comportement du système réel. Dans le projet, `jumeaux-chauds` joue ce rôle en simulant un parc de serveurs avec télémétrie MQTT, états machines (on/degraded/off), et protection thermique automatique.

Les jumeaux numériques sont aujourd'hui largement utilisés dans l'industrie (GE, Siemens) et les datacenters (Google DeepMind a réduit de 40 % la consommation de refroidissement de ses datacenters via un RL sur jumeau numérique).

---

## 2. Stockage et Gestion de Données de Séries Temporelles

### 2.1 TimescaleDB

**TimescaleDB** est une extension PostgreSQL open source spécialisée dans les séries temporelles. Elle combine la puissance de SQL avec des optimisations spécifiques au temps.

**Fonctionnalités principales :**
- **Hypertables** : partitionnement automatique des données par intervalles de temps.
- **Compression native** : réduction jusqu'à 90 % de l'espace disque.
- **Continuous Aggregates** : vues matérialisées mises à jour automatiquement pour les agrégations temporelles.
- **Retention policies** : suppression automatique des données anciennes.
- **Requêtes temps** : fonctions natives `time_bucket()`, `first()`, `last()`.

**Cas d'usage dans le projet :**
- Stockage des télémétries (température, RPM, puissance) horodatées.
- Requêtes d'agrégation pour le feature engineering (moyennes glissantes, dérivées).
- Intégration native avec Grafana pour la visualisation.

**Exemple de requête :**
```sql
SELECT time_bucket('5 seconds', time) AS bucket,
       AVG(temperature) AS avg_temp,
       MAX(temperature) AS max_temp
FROM telemetry
WHERE machine_id = 'machine_3'
GROUP BY bucket
ORDER BY bucket DESC;
```

### 2.2 DuckDB

**DuckDB** est un moteur de base de données analytique embarqué (in-process), sans serveur, optimisé pour les requêtes OLAP sur des fichiers locaux (CSV, Parquet, JSON).

**Avantages :**
- Très rapide pour les analyses ad hoc sur des fichiers locaux.
- Pas de serveur à déployer — s'intègre directement dans Python, R, ou Julia.
- Support natif de Parquet et Arrow.
- Idéal pour l'exploration de datasets et le prototypage rapide.

**Exemple Python :**
```python
import duckdb
result = duckdb.query("SELECT * FROM 'data/telemetry.parquet' WHERE temperature > 80").df()
```

### 2.3 Apache Parquet

**Apache Parquet** est un format de fichier columnar open source (projet Apache), conçu pour l'analyse efficace de grands volumes de données.

**Caractéristiques :**
- **Stockage colonnaire** : lecture uniquement des colonnes nécessaires → performances analytiques excellentes.
- **Compression intégrée** : Snappy, GZIP, Brotli.
- **Schéma embarqué** : les métadonnées du schéma sont incluses dans le fichier.
- **Interopérabilité** : compatible avec Pandas, Spark, DuckDB, PyArrow, Hive...

**Usage dans le projet :**
- Export des datasets train/validation/test par épisode ou seed pour la reproductibilité.
- Versionnage des datasets (nommage avec date, seed, paramètres du scénario).

```python
import pandas as pd
df.to_parquet('data/train_seed42_episode1.parquet', index=False)
df_loaded = pd.read_parquet('data/train_seed42_episode1.parquet')
```

---

## 3. Machine Learning pour Séries Temporelles

### 3.1 Feature Engineering Temporel

Le feature engineering est une étape cruciale pour transformer des séries temporelles brutes en variables exploitables par les modèles de ML classiques.

**Catégories de features pertinentes pour le projet :**

| Type | Exemples | Intérêt |
|---|---|---|
| Lag features | `temp_t-1`, `temp_t-5` | Capturer l'historique récent |
| Rolling statistics | `temp_mean_30s`, `temp_std_30s` | Tendances lissées |
| Dérivées | `delta_temp_5s`, `temp_rate` | Vitesse de changement |
| Marge au seuil | `margin_to_shutdown` | Proximité du danger |
| Durée | `time_in_hot_zone` | Persistance des états |
| Énergie | `power_cumulative`, `PUE_estimate` | Efficacité énergétique |

**Bibliothèques Python spécialisées :**
- **tsfresh** : extraction automatique de centaines de features temporelles.
- **featuretools** : feature engineering automatisé.
- **Pandas** : rolling windows, shift, diff — suffisants pour ce projet.

### 3.2 Scikit-learn

**scikit-learn** est la bibliothèque de référence pour le machine learning classique en Python.

**Modèles pertinents pour la prédiction de pannes :**
- **Logistic Regression** : baseline interprétable, rapide à entraîner.
- **Random Forest** : robuste, gère bien les features corrélées, fournit l'importance des variables.
- **SVM** : efficace sur données tabulaires avec bon scaling.
- **Isolation Forest** : détection d'anomalies non supervisée.

**Outils d'évaluation clés :**
```python
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score
from sklearn.model_selection import TimeSeriesSplit  # Important pour les séries temporelles !
```

**Attention** : Pour les séries temporelles, il ne faut **jamais** utiliser une validation croisée aléatoire (risque de data leakage). Utiliser `TimeSeriesSplit` ou une séparation stricte par épisode/date.

### 3.3 XGBoost

**XGBoost** (eXtreme Gradient Boosting) est un algorithme de gradient boosting très performant, lauréat de nombreuses compétitions Kaggle.

**Principe :** Ensemble d'arbres de décision entraînés séquentiellement, chaque arbre corrigeant les erreurs du précédent.

**Avantages :**
- Gestion native des valeurs manquantes.
- Régularisation L1/L2 intégrée.
- Très rapide grâce à l'optimisation du calcul des gradients.
- Support GPU (`tree_method='gpu_hist'`).

**Paramètres importants :**
- `n_estimators` : nombre d'arbres.
- `max_depth` : profondeur maximale (contrôle l'overfitting).
- `learning_rate` : taux d'apprentissage.
- `scale_pos_weight` : gestion du déséquilibre de classes (crucial pour les pannes rares).

```python
from xgboost import XGBClassifier
model = XGBClassifier(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.05,
    scale_pos_weight=10,  # si 10x plus de négatifs que positifs
    eval_metric='aucpr'
)
```

### 3.4 LightGBM

**LightGBM** (Light Gradient Boosting Machine) est développé par Microsoft et offre des performances similaires à XGBoost avec un entraînement souvent plus rapide.

**Différences clés vs XGBoost :**
- Croissance des arbres par feuille (leaf-wise) plutôt que par niveau → plus rapide mais peut overfitter sur petits datasets.
- Histogram-based splitting → mémoire réduite.
- Support natif des features catégorielles.

```python
import lightgbm as lgb
model = lgb.LGBMClassifier(
    n_estimators=1000,
    learning_rate=0.05,
    num_leaves=31,
    class_weight='balanced'
)
```

**Comparaison XGBoost vs LightGBM :**

| Critère | XGBoost | LightGBM |
|---|---|---|
| Vitesse d'entraînement | Rapide | Très rapide |
| Performance | Très bonne | Très bonne |
| Dataset volumineux | Bien | Excellent |
| Interprétabilité | Bonne | Bonne |
| Gestion catégorielles | Nécessite encoding | Natif |

### 3.5 Métriques d'évaluation pour la prédiction de pannes

La prédiction de pannes est un problème de **classification déséquilibrée** (les pannes sont rares). Les métriques appropriées sont :

- **Precision** : parmi les alertes levées, combien sont réelles ? (éviter les faux positifs — coût opérationnel).
- **Recall** : parmi les vraies pannes, combien ont été détectées ? (éviter les faux négatifs — coût sécurité). **Le recall doit être prioritaire.**
- **F1-score** : moyenne harmonique precision/recall.
- **PR-AUC** (Area Under Precision-Recall Curve) : plus pertinent que la ROC-AUC sur données déséquilibrées.
- **Temps moyen d'anticipation** : délai moyen entre l'alerte et l'incident réel → métriqué spécifique au projet.

### 3.6 Approches de contrôle et de régulation

**Contrôle à seuils (rule-based) :** Simple et interprétable. Ex. : `if temp > 75°C then fan_speed = HIGH`. Sert de baseline obligatoire.

**Contrôleur PID :** Proportionnel-Intégral-Dérivé. Régulation classique de l'automatique industrielle. Robuste et bien compris, mais ne s'adapte pas aux contextes changeants.

**Apprentissage supervisé de politique :** Entraîner un classifieur sur des données historiques labelisées avec la "meilleure" action. Nécessite une politique experte ou optimale pour générer les labels.

**Contrôle à score multi-objectif :**
$$J(t) = \alpha \cdot \text{risk}(t) + \beta \cdot \text{heat}(t) + \gamma \cdot \text{energy}(t) + \delta \cdot |\Delta \text{RPM}_t|$$
Permet de pondérer explicitement sécurité, température et consommation.

**Bandits contextuels :** Approche intermédiaire entre règles et RL. L'agent choisit une action (vitesse de ventilateur) en fonction du contexte (état thermique) et observe la récompense (température obtenue, consommation). Bibliothèques : `vowpalwabbit`, `mabwiser`.

**Reinforcement Learning (option avancée) :** L'agent apprend une politique de contrôle par interactions avec l'environnement. Bibliothèques : `Stable-Baselines3`, `RLlib`. Pertinent si le simulateur peut générer suffisamment d'épisodes d'entraînement. Algorithmes recommandés : PPO, SAC pour les actions continues ou discrètes.

---

## 4. Déploiement et Observabilité

### 4.1 Docker et Conteneurisation

**Docker** permet d'empaqueter une application et toutes ses dépendances dans un conteneur portable et reproductible.

**Concepts clés :**
- **Image** : snapshot immuable d'un environnement (Dockerfile → image).
- **Conteneur** : instance en cours d'exécution d'une image.
- **Docker Compose** : orchestration multi-conteneurs via un fichier `docker-compose.yml`.
- **Volumes** : persistance des données entre redémarrages.
- **Networks** : communication entre conteneurs (ex. service d'ingestion ↔ TimescaleDB ↔ Grafana).

**Structure docker-compose typique pour le projet :**
```yaml
version: '3.8'
services:
  jumeaux-chauds:
    image: jumeaux-chauds:latest
    ports:
      - "1883:1883"  # MQTT broker
  
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_PASSWORD: password
    volumes:
      - ts_data:/var/lib/postgresql/data
  
  ingest:
    build: ./ingest
    depends_on:
      - jumeaux-chauds
      - timescaledb
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"

volumes:
  ts_data:
```

### 4.2 Prometheus

**Prometheus** est un système de monitoring open source (CNCF) basé sur un modèle pull : il collecte périodiquement des métriques exposées par les services via des endpoints HTTP (`/metrics`).

**Concepts :**
- **Métriques** : Counter, Gauge, Histogram, Summary.
- **PromQL** : langage de requête pour interroger les métriques.
- **Alertmanager** : déclenchement d'alertes basées sur des règles PromQL.

**Usage dans le projet :**
- Exposer des métriques custom depuis le service de supervision (nombre d'alertes levées, latence de prédiction, consommation estimée).
- Monitorer la santé du pipeline d'ingestion (messages MQTT reçus/s, erreurs de parsing).

```python
from prometheus_client import Counter, Gauge, start_http_server

alerts_total = Counter('fan_alerts_total', 'Nombre total d alertes de panne')
current_temperature = Gauge('machine_temperature_celsius', 'Température courante', ['machine_id'])
```

### 4.3 Grafana

**Grafana** est la plateforme de visualisation de référence pour les métriques et séries temporelles. Elle s'intègre nativement avec TimescaleDB (via PostgreSQL datasource) et Prometheus.

**Fonctionnalités clés :**
- Dashboards dynamiques avec variables et filtres.
- Alerting intégré (seuils, anomalies).
- Annotations : marquer les événements (shutdown, alerte ML) directement sur les graphiques.
- Panels variés : graphiques temporels, heatmaps, jauges, tables.

**Dashboards utiles pour le projet :**
1. Vue temps réel : température par machine, RPM, état (on/degraded/off).
2. Prédictions ML : probabilité de panne en temps réel, horizon d'anticipation.
3. Efficacité énergétique : consommation instantanée, cumulative, PUE estimé.
4. Comparaison stratégies : baseline vs contrôleur ML — incidents, consommation.

---

## 5. Architecture Globale de Référence

L'architecture recommandée pour le projet suit un pattern **Lambda/Kappa simplifié** :

```
jumeaux-chauds (simulateur)
        │ MQTT
        ▼
  [Subscriber MQTT]  ──parse/normalize──►  [TimescaleDB]
        │                                       │
        ▼                                  [Grafana]
  [Feature Engine]
        │
        ├──► [Modèle prédiction pannes]  ──► alerte
        │              (XGBoost/LightGBM)
        │
        └──► [Contrôleur ventilateurs]   ──► REST API → jumeaux-chauds
                  (classifieur / PID / bandit)
```

**Flux de données :**
1. Le simulateur publie la télémétrie sur MQTT toutes les N secondes.
2. Le subscriber collecte, parse et stocke dans TimescaleDB.
3. Le moteur de features lit les dernières N secondes et calcule les features.
4. Le modèle de prédiction évalue le risque de panne à horizon 60s.
5. Le contrôleur choisit la consigne RPM et l'envoie via l'API REST.
6. Les décisions et métriques sont loggées et visualisées dans Grafana.

---

## 6. État de l'Art — Maintenance Prédictive et Gestion Thermique

### 6.1 Maintenance Prédictive Industrielle

La **maintenance prédictive** (Predictive Maintenance, PdM) est une approche qui consiste à anticiper les pannes à partir de données de capteurs, plutôt que d'attendre la panne (correctif) ou d'intervenir à intervalles fixes (préventif).

**Niveaux de maturité :**
1. **Condition-based monitoring** : alertes sur seuils fixes.
2. **Statistical process control** : contrôle statistique (cartes de contrôle Shewhart).
3. **ML-based PdM** : prédiction d'anomalies et de durée de vie restante (RUL — Remaining Useful Life).
4. **Deep learning PdM** : LSTM, Transformers pour séries temporelles complexes.

**Datasets de référence :**
- **NASA CMAPSS** : dégradation de moteurs d'avion — benchmark classique pour la prédiction de RUL.
- **C-MAPSS** : version étendue avec conditions multiples.

### 6.2 Optimisation Thermique de Datacenters

**PUE (Power Usage Effectiveness)** : métrique standard d'efficacité énergétique des datacenters.
$$PUE = \frac{\text{Énergie totale du datacenter}}{\text{Énergie des équipements IT}}$$
Un PUE de 1.0 est idéal (toute l'énergie va aux serveurs). La moyenne mondiale est ~1.58.

**Travaux marquants :**
- **Google DeepMind (2016)** : réduction de 40 % de la consommation de refroidissement via Deep RL. Le modèle prédit la consommation future et recommande des actions sur les systèmes de refroidissement.
- **Meta (2022)** : optimisation des datacenters via ML pour réduire le PUE.
- **Microsoft** : recherche sur les datacenters sous-marins (Project Natick) avec monitoring thermique avancé.

**Algorithmes de contrôle avancés :**
- **MPC (Model Predictive Control)** : planification sur un horizon glissant avec modèle dynamique du système.
- **DDPG / SAC** : RL à actions continues, adapté au contrôle de vitesse de ventilateur.
- **Multi-agent RL** : un agent par machine/cluster, coordination globale.

---

## 7. Bonnes Pratiques et MLOps

### 7.1 Reproductibilité

- Fixer les seeds aléatoires (`random_state`, `numpy.random.seed`, `torch.manual_seed`).
- Versionner les datasets avec des identifiants (seed, scénario, date).
- Sauvegarder les hyperparamètres dans des fichiers de config (YAML/JSON).
- Utiliser MLflow ou DVC pour le tracking des expériences.

### 7.2 Versionnage de modèles

```python
import joblib
# Sauvegarder
joblib.dump(model, 'models/failure_prediction/xgb_v1.0_seed42.pkl')
# Charger
model = joblib.load('models/failure_prediction/xgb_v1.0_seed42.pkl')
```

### 7.3 Monitoring en production

- **Data drift** : surveiller si la distribution des features change dans le temps (alibi-detect, evidently).
- **Concept drift** : les performances du modèle peuvent se dégrader si le comportement du système évolue.
- **Feedback loop** : comparer les prédictions aux événements réels et réentraîner périodiquement.

---

## 8. Ressources et Références

| Domaine | Ressource | URL |
|---|---|---|
| MQTT | Spécification officielle | https://mqtt.org/ |
| MQTT | Mosquitto Broker | https://mosquitto.org/ |
| Streaming | Apache Kafka | https://kafka.apache.org/ |
| Séries temporelles | TimescaleDB | https://www.timescale.com/ |
| Analytique locale | DuckDB | https://duckdb.org/ |
| Format colonnaire | Apache Parquet | https://parquet.apache.org/ |
| ML classique | scikit-learn | https://scikit-learn.org/ |
| Gradient Boosting | XGBoost | https://xgboost.readthedocs.io/ |
| Gradient Boosting | LightGBM | https://lightgbm.readthedocs.io/ |
| Séries temporelles Pandas | Documentation officielle | https://pandas.pydata.org/docs/user_guide/timeseries.html |
| Conteneurisation | Docker | https://www.docker.com/ |
| Monitoring | Prometheus | https://prometheus.io/ |
| Visualisation | Grafana | https://grafana.com/ |
| Simulateur projet | jumeaux-chauds | https://github.com/tristanv/jumeaux-chauds |

---

## Conclusion

Cette veille technologique couvre l'ensemble des briques nécessaires à la réalisation du projet "Juste des ventilateurs". Les technologies identifiées forment un écosystème cohérent : **MQTT** pour la collecte temps réel, **TimescaleDB** pour le stockage de séries temporelles, **XGBoost/LightGBM** pour la prédiction de pannes, un contrôleur à score ou bandit contextuel pour la régulation, et **Grafana/Prometheus** pour l'observabilité. L'ensemble est conteneurisé via **Docker Compose** pour garantir la reproductibilité.

Les principaux défis techniques à anticiper sont : la gestion du déséquilibre de classes (pannes rares), la prévention du data leakage dans la validation des modèles de séries temporelles, et le compromis entre sécurité thermique et efficacité énergétique dans la fonction de coût du contrôleur.
