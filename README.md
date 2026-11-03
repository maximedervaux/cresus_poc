# POC « Crésus » – BI prédictive de trésorerie (ZF Banque)

Implémentation du Proof of Concept décrit dans le document MOE : chaîne complète
**sources hétérogènes → ETL Python → MySQL (étoile) → Prophet / ARIMA à 30 jours → scénarios de stress → Power BI**,
sur 3 filiales : France (EUR), Canada (CAD), Côte d'Ivoire (XAF).

## Architecture

Diagrammes détaillés (architecture, ETL, modèle de données, prédiction, stress, Power BI) : [docs/DIAGRAMMES.md](docs/DIAGRAMMES.md).

```
data/sources/                     extract_marche.py         -> taux_change.csv, valeur_usd.csv (API BCE réelle),
  flux_tresorerie_FR|CA|CI.csv                                  taux_directeurs.csv
  taux_change.csv ...             generer_flux_filiales.py  -> extractions ERP simulées (formats hétérogènes)
        │
        ▼  etl.py                 staging (stg_*) → nettoyage, dédoublonnage, normalisation, conversion USD
MySQL cresus_poc                  zone REPORTING : dim_filiale, dim_devise, dim_calendrier, dim_type_flux,
        │                                          fait_flux_tresorerie, fait_taux
        ▼  prediction.py          zone PREDICTIVE: fait_prevision (backtest + production), fait_prevision_taux,
        ▼  stress.py                               perf_modele, fait_scenario_stress
        ▼  restitution.py         vues v_* pour Power BI
Power BI                          powerbi/GUIDE_POWERBI.md
```

## Exécution

Prérequis : Python 3.11+, MySQL 8+ démarré (`mysql.server start`).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_pipeline.py                  # chaîne complète (~5 s)
.venv/bin/python run_pipeline.py --sans-sources   # sans re-télécharger/régénérer les sources
```

Connexion par défaut : `root` sans mot de passe sur `127.0.0.1:3306`. Pour la changer :
`export CRESUS_DB_SERVER="mysql+pymysql://user:motdepasse@hote:3306"`.
La base `cresus_poc` est **recréée à chaque exécution** (POC idempotent).

## Résultats obtenus

**Qualité des données (ETL)**, par fichier filiale : 22 doublons supprimés, 13 lignes non pertinentes filtrées
(opérations annulées, virements internes, lignes de test), 9 lignes rejetées (montant manquant).

**Backtest** : prévision des 30 derniers jours (02/10 → 31/10/2026) comparée au réalisé.

| Filiale | Modèle retenu | MAE modèle | MAE prévision manuelle | Réduction de l'erreur |
|---|---|---|---|---|
| France | ARIMA | 7,4 M EUR | 9,1 M EUR | **-19 %** |
| Canada | Prophet | 3,7 M CAD | 6,2 M CAD | **-41 %** |
| Côte d'Ivoire | Prophet | 0,72 Md XAF | 1,35 Md XAF | **-46 %** |

**Stress à J+30** : un retrait massif de dépôts (+30 %) fait passer la Côte d'Ivoire sous son seuil d'alerte
pendant 22 jours sur 30. Les chocs de change (-10 / -20 %) réduisent la valeur des positions en USD sans
créer de tension de liquidité locale. La hausse de +200 pb des taux directeurs a un impact modéré.

**Projection des devises** : ARIMA (1,1,1) converge vers une marche aléatoire (variation ≈ 0, NEUTRE) ;
Prophet extrapole la tendance (EUR et XAF FAVORABLE, CAD DÉFAVORABLE). L'écart entre les deux modèles
illustre la faible prévisibilité du change à 30 jours : à utiliser comme signal, pas comme certitude.

## Choix de mise en œuvre et écarts au MOE

| # | MOE | Choix retenu | Raison |
|---|---|---|---|
| 1 | `montant_eur`, `taux_change_eur` libellés « converti en USD » | `montant_usd`, `taux_change_usd` | Devise de reporting = USD (§2.2.2) ; noms alignés |
| 2 | « 2 schémas » puis « 3 schémas » (staging cité) | 3 zones : `stg_*`, étoile, prédictif, dans la base unique `cresus_poc` | Sous MySQL, schéma = base : préfixes de tables |
| 3 | `DIM_CALENDRIER.pays` | `ouvre_fra`, `ouvre_can`, `ouvre_civ` | `date_id` unique est incompatible avec une ligne par pays ; un drapeau jour ouvré par pays permet le même usage |
| 4 | – | `dim_filiale.seuil_alerte` | Nécessaire pour la vue « devises à faible stock » (§2.2.5) |
| 5 | `FAIT_PREVISION` | + `type_run` (BACKTEST / PRODUCTION) | Distinguer l'évaluation des modèles de la prévision opérationnelle |
| 6 | – | `fait_prevision_taux`, `perf_modele` | Projection des taux (vue 2 §2.2.5) et comparaison des modèles (§2.1.2) |
| 7 | `FAIT_SCENARIO_STRESS.montant_stresse` | + `montant_base`, `position_base_usd`, `position_stressee_usd` (USD) | Comparer base et stress sans calcul complexe dans Power BI |
| 8 | – | Type de flux `REPORT_A_NOUVEAU` | Solde d'ouverture, nécessaire pour reconstituer la position |
| 9 | Côte d'Ivoire : XAF | Conservé | ⚠️ La Côte d'Ivoire utilise en réalité le **XOF** (BCEAO) ; le XAF est la zone BEAC (Cameroun). Même parité fixe avec l'euro, donc aucun impact sur les calculs. À corriger dans les livrables. |

## Limites du POC

- **Flux des filiales simulés** (générateur à graine fixe, reproductible) : les gains mesurés valident la
  chaîne technique, pas une performance réelle. Les **taux de change sont réels** (BCE). Les taux directeurs
  EUR et CAD sont réels (API BCE et Banque du Canada) ; ceux de la BEAC (XAF), sans API, sont saisis manuellement.
- Données externes en différé (batch quotidien), pas en temps réel (§2.1.5).
- Règles de stress volontairement simples et documentées dans `stress.py` (taux d'indexation, fenêtre de 90 jours).
- En cible : Data Warehouse / Data Lake, orchestrateur (Airflow…), toutes les
  filiales et devises, gouvernance et traçabilité des modèles (exigence réglementaire).
