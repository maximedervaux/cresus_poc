# Diagrammes du POC Crésus

1. [Architecture globale](#1-architecture-globale)
2. [Orchestration de la chaîne](#2-orchestration-de-la-chaîne)
3. [ETL : homogénéisation des sources](#3-etl--homogénéisation-des-sources)
4. [Modèle de données](#4-modèle-de-données)
5. [Moteur prédictif](#5-moteur-prédictif)
6. [Scénarios de stress](#6-scénarios-de-stress)
7. [Restitution Power BI](#7-restitution-power-bi)

---

## 1. Architecture globale

Les 5 étapes du MOE (§2.2) : sources → ETL → stockage → prédiction → restitution.

```mermaid
flowchart LR
    subgraph SRC["Sources"]
        direction TB
        FR["flux_tresorerie_FR.csv<br/>France · EUR"]
        CA["flux_tresorerie_CA.csv<br/>Canada · CAD"]
        CI["flux_tresorerie_CI.csv<br/>Côte d'Ivoire · XAF"]
        FX["taux_change.csv<br/>valeur_usd.csv"]
        TD["taux_directeurs.csv"]
        JF["calendrier_jours_feries.csv"]
    end

    GEN["generer_flux_filiales.py<br/>ERP simulés"] --> FR & CA & CI & JF
    BCE(["API BCE<br/>Frankfurter"]) --> EXT["extract_marche.py"] --> FX & TD

    SRC --> ETL["etl.py"]

    subgraph DB["MySQL · cresus_poc"]
        direction TB
        STG[("STAGING<br/>stg_*")]
        REP[("REPORTING<br/>dim_* · fait_flux_tresorerie · fait_taux")]
        PRD[("PREDICTIVE<br/>fait_prevision · fait_prevision_taux<br/>perf_modele · fait_scenario_stress")]
        VUES[("Vues v_*")]
    end

    ETL --> STG
    ETL --> REP
    REP --> PRED["prediction.py<br/>Prophet · ARIMA"] --> PRD
    PRD --> STRESS["stress.py"] --> PRD
    REP & PRD --> RES["restitution.py"] --> VUES
    VUES --> PBI["Power BI"]

    classDef ext fill:#e8f4ea,stroke:#4a8a5a
    classDef py fill:#fde8e8,stroke:#b55
    classDef out fill:#e6eefa,stroke:#4a6fa5
    class BCE,FR,CA,CI,FX,TD,JF ext
    class GEN,EXT,ETL,PRED,STRESS,RES py
    class PBI out
```

---

## 2. Orchestration de la chaîne

`run_pipeline.py` enchaîne les étapes ; `--sans-sources` saute les deux premières.

```mermaid
sequenceDiagram
    autonumber
    participant O as run_pipeline.py
    participant M as extract_marche.py
    participant G as generer_flux_filiales.py
    participant E as etl.py
    participant DB as MySQL cresus_poc
    participant P as prediction.py
    participant S as stress.py
    participant R as restitution.py

    O->>M: main()
    M->>M: GET API BCE (EUR/USD, EUR/CAD)
    M-->>O: taux_change.csv, valeur_usd.csv, taux_directeurs.csv
    O->>G: main()
    G-->>O: flux_tresorerie_FR/CA/CI.csv, calendrier_jours_feries.csv
    O->>E: main()
    E->>DB: DROP + CREATE DATABASE (sql/schema.sql)
    E->>DB: stg_* (données brutes)
    E->>DB: dim_*, fait_taux, fait_flux_tresorerie, etl_controle_qualite
    O->>P: main()
    P->>DB: lit flux, calendrier, taux
    P->>P: backtest + production (Prophet, ARIMA)
    P->>DB: fait_prevision, fait_prevision_taux, perf_modele
    O->>S: main()
    S->>DB: lit prévision du modèle retenu, positions, spot
    S->>DB: fait_scenario_stress
    O->>R: main()
    R->>DB: CREATE VIEW v_* (sql/vues.sql)
```

---

## 3. ETL : homogénéisation des sources

Chaque filiale a son propre format ; l'ETL les ramène à une structure commune.

```mermaid
flowchart TB
    subgraph IN["Fichiers bruts (lus en texte, chargés tels quels en stg_*)"]
        direction LR
        FR["FR<br/>sép. ; · décimale ,<br/>JJ/MM/AAAA · cp1252<br/>libellés français"]
        CA["CA<br/>sép. , · MM/JJ/AAAA<br/>libellés anglais, casse variable<br/>décaissements négatifs"]
        CI["CI<br/>sép. | · AAAAMMJJ<br/>codes courts · sens C/D<br/>milliers séparés par espace"]
    end

    IN --> N1["Suppression des espaces parasites"]
    N1 --> N2["Dédoublonnage<br/>lignes strictement identiques"]
    N2 --> N3{"Ligne pertinente ?"}
    N3 -- "non : Annulé (FR) · Internal transfer (CA) · TEST (CI)" --> X1["compteur non_pertinentes"]
    N3 -- oui --> N4["Standardisation<br/>date → AAAA-MM-JJ<br/>montant → numérique<br/>libellé → référentiel Groupe<br/>statut → REALISE / PREVISIONNEL"]
    N4 --> N5{"CI : sens C/D cohérent<br/>avec le type de flux ?"}
    N5 -- non --> X2
    N5 -- oui --> N6{"Champs complets et reconnus ?"}
    N6 -- non --> X2["compteur rejets"]
    N6 -- oui --> N7["montant = valeur absolue<br/>(sens porté par dim_type_flux)"]
    N7 --> N8["Conversion USD<br/>montant × cours du jour<br/>(dernier cours connu pour les dates futures)"]
    N8 --> OUT[("fait_flux_tresorerie")]
    X1 & X2 --> Q[("etl_controle_qualite")]

    subgraph TX["Taux"]
        direction TB
        T1["EUR/USD (BCE) · EUR/CAD (BCE)<br/>EUR/XAF = 655,957 (parité fixe)"]
        T2["Valeur USD d'une unité :<br/>EUR = EUR/USD<br/>CAD = EUR/USD ÷ EUR/CAD<br/>XAF = EUR/USD ÷ 655,957"]
        T3["Week-ends et fériés BCE :<br/>report du dernier cours"]
        T4["Taux directeur en vigueur<br/>(dernière décision ≤ date)"]
        T1 --> T2 --> T3 --> T4
    end
    T4 --> FT[("fait_taux")]
    FT -. cours du jour .-> N8
```

---

## 4. Modèle de données

Constellation de faits partageant les dimensions (zone REPORTING + PREDICTIVE).

```mermaid
erDiagram
    dim_devise ||--o{ dim_filiale : "devise principale"
    dim_filiale ||--o{ fait_flux_tresorerie : "filiale"
    dim_devise ||--o{ fait_flux_tresorerie : "devise"
    dim_type_flux ||--o{ fait_flux_tresorerie : "nature"
    dim_calendrier ||--o{ fait_flux_tresorerie : "date_id"
    dim_calendrier ||--o{ fait_taux : "date_id"
    dim_devise ||--o{ fait_taux : "devise"
    dim_calendrier ||--o{ fait_prevision : "date_cible"
    dim_filiale ||--o{ fait_prevision : "filiale"
    dim_devise ||--o{ fait_prevision : "devise"
    dim_calendrier ||--o{ fait_prevision_taux : "date_cible"
    dim_devise ||--o{ fait_prevision_taux : "devise"
    dim_filiale ||--o{ perf_modele : "filiale"
    dim_calendrier ||--o{ fait_scenario_stress : "date_cible"
    dim_filiale ||--o{ fait_scenario_stress : "filiale"
    dim_devise ||--o{ fait_scenario_stress : "devise"

    dim_devise {
        char3 code_devise PK "EUR, CAD, XAF, USD"
        varchar libelle_devise
    }
    dim_filiale {
        int id_filiale PK
        varchar nom_filiale UK
        char3 pays "ISO alpha-3"
        varchar zone_geo
        char3 devise_principale FK
        decimal seuil_alerte "devise locale"
    }
    dim_calendrier {
        int date_id PK "AAAAMMJJ"
        date date UK
        tinyint jour
        tinyint mois
        smallint annee
        tinyint jour_semaine
        bool ouvre_fra
        bool ouvre_can
        bool ouvre_civ
    }
    dim_type_flux {
        int id_type_flux PK
        varchar libelle UK
        varchar sens "ENCAISSEMENT / DECAISSEMENT"
    }
    fait_flux_tresorerie {
        int id_flux PK
        int date_id FK
        int id_filiale FK
        char3 code_devise FK
        int id_type_flux FK
        decimal montant "positif, devise locale"
        decimal montant_usd
        varchar statut "REALISE / PREVISIONNEL"
    }
    fait_taux {
        int date_id PK, FK
        char3 code_devise PK, FK
        decimal taux_change_usd
        decimal taux_directeur "%"
    }
    fait_prevision {
        int id_prevision PK
        varchar type_run "BACKTEST / PRODUCTION"
        date date_generation
        date date_cible FK
        int id_filiale FK
        char3 code_devise FK
        varchar modele "PROPHET / ARIMA"
        decimal montant_prevu "flux net"
        decimal borne_basse "IC 80%"
        decimal borne_haute "IC 80%"
    }
    fait_prevision_taux {
        int id_prevision_taux PK
        date date_generation
        date date_cible FK
        char3 code_devise FK
        varchar modele
        decimal taux_prevu
        decimal borne_basse
        decimal borne_haute
    }
    perf_modele {
        int id_filiale PK, FK
        varchar modele PK "PROPHET / ARIMA / MANUEL"
        date date_generation
        int nb_jours
        decimal mae
        decimal wape_pct
        decimal ecart_position_j30
        bool retenu
    }
    fait_scenario_stress {
        int id_scenario PK
        varchar libelle_scenario
        date date_cible FK
        int id_filiale FK
        char3 code_devise FK
        varchar type_choc
        decimal valeur_choc
        decimal montant_base "USD"
        decimal montant_stresse "USD"
        decimal position_base_usd
        decimal position_stressee_usd
    }
```

---

## 5. Moteur prédictif

Cible : **flux net journalier** (encaissements − décaissements) par filiale, horizon 30 jours.

```mermaid
flowchart TB
    F[("fait_flux_tresorerie<br/>REALISE, hors REPORT_A_NOUVEAU")] --> S["Série flux net journalier<br/>par filiale (0 les jours sans flux)"]
    C[("dim_calendrier")] --> X["Variables calendaires connues à l'avance<br/>ouvre · debut_mois · echeance · salaire<br/>impot · fin_mois · vendredi · decembre"]

    S & X --> BT
    S & X --> PR

    subgraph BT["1 · BACKTEST : évaluer"]
        direction TB
        B1["Entraînement jusqu'au 01/10/2026"]
        B2["Prévision 02/10 → 31/10/2026"]
        B3["Comparaison au réalisé<br/>MAE · WAPE · écart de position à J+30"]
        B1 --> B2 --> B3
    end

    subgraph PR["2 · PRODUCTION : prévoir"]
        direction TB
        P1["Entraînement jusqu'au 31/10/2026"]
        P2["Prévision 01/11 → 30/11/2026"]
        P1 --> P2
    end

    subgraph MOD["Modèles (×2 dans chaque run)"]
        direction LR
        M1["Prophet<br/>+ régresseurs calendaires<br/>IC 80 %"]
        M2["ARIMA(1,0,1)<br/>+ variables exogènes<br/>IC 80 %"]
    end
    MOD -.-> BT & PR

    MAN[("Prévision manuelle des trésoriers<br/>statut PREVISIONNEL")] --> B3
    B3 --> PM[("perf_modele<br/>retenu = WAPE minimal<br/>par filiale")]
    B2 & P2 --> J["Jours fermés forcés à 0"] --> FP[("fait_prevision")]

    T[("fait_taux")] --> TX["Cours USD par devise"] --> TM["Prophet (tendance)<br/>ARIMA(1,1,1)"] --> FPT[("fait_prevision_taux<br/>J+1 → J+30")]
```

---

## 6. Scénarios de stress

Appliqués à la prévision de production du **modèle retenu**, montants en USD au cours spot.

```mermaid
flowchart TB
    IN1[("fait_prevision<br/>modèle retenu, PRODUCTION")] --> BASE["Flux de base par jour"]
    IN2["Position de départ<br/>somme du réalisé"] --> POS
    IN3["Cours spot + taux directeur actuel<br/>(dernière ligne de fait_taux)"] --> CHOC
    IN4["Moyennes par jour ouvré sur 90 j<br/>intérêts versés / reçus, retraits clients"] --> CHOC

    BASE --> CHOC{"type_choc"}
    CHOC -- "TAUX_CHANGE −10 / −20 %" --> C1["Flux inchangés<br/>facteur de change = 1 + choc"]
    CHOC -- "TAUX_DIRECTEUR +2 pts" --> C2["Δ/jour ouvré = − intérêts versés × 2/taux actuel<br/>+ intérêts reçus × 2/taux actuel × 30 %"]
    CHOC -- "RETRAIT_DEPOTS +30 %" --> C3["Δ/jour ouvré = − retraits moyens × 30 %"]

    C1 & C2 & C3 --> POS["Position stressée<br/>= (position départ + Σ flux stressés) × spot × facteur de change"]
    POS --> OUT[("fait_scenario_stress")]
    OUT --> V["v_stress_synthese<br/>impact à J+30 · position minimale<br/>nb de jours sous le seuil"]
    V --> NOTE["Pour un choc de change, le seuil est dévalué<br/>du même facteur : la liquidité locale ne change pas"]
```

---

## 7. Restitution Power BI

Des tables et vues MySQL aux pages du rapport (MOE §2.2.5).

```mermaid
flowchart LR
    subgraph V["Vues MySQL"]
        direction TB
        VF["v_flux_net_journalier"]
        VR["v_position_realisee"]
        VP["v_position_projetee"]
        VB["v_backtest"]
        VT["v_projection_taux"]
        VS["v_stress_synthese"]
    end
    VF --> VR & VP & VB

    subgraph T["Tables"]
        direction TB
        FPT[("fait_prevision_taux")]
        PM[("perf_modele")]
        FSS[("fait_scenario_stress")]
        QC[("etl_controle_qualite")]
    end

    subgraph PBI["Rapport Power BI"]
        direction TB
        P1["1 · Actifs & liquidité<br/>positions, seuils, devises à faible stock"]
        P2["2 · Projection des devises<br/>FAVORABLE / DÉFAVORABLE / NEUTRE"]
        P3["3 · Fiabilité des prévisions<br/>modèles vs prévision manuelle"]
        P4["4 · Scénarios de stress"]
        P5["5 · Qualité des données"]
    end

    VR & VP --> P1
    VT & FPT --> P2
    VB & PM --> P3
    VS & FSS --> P4
    QC --> P5
```
