-- =====================================================================
-- POC Crésus - base cresus_poc (MOE §2.4 à §2.6)
--   Zone STAGING   : tables stg_*  (données brutes, créées par l'ETL)
--   Zone REPORTING : dim_* / fait_flux_tresorerie / fait_taux (étoile)
--   Zone PREDICTIVE: fait_prevision / fait_prevision_taux /
--                    fait_scenario_stress / perf_modele
-- MySQL ne distinguant pas schéma et base, les zones sont matérialisées
-- par des préfixes dans une base unique.
-- =====================================================================
DROP DATABASE IF EXISTS cresus_poc;
CREATE DATABASE cresus_poc CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cresus_poc;

-- ---------------------------- DIMENSIONS -----------------------------
CREATE TABLE dim_devise (
    code_devise     CHAR(3)      PRIMARY KEY,
    libelle_devise  VARCHAR(50)  NOT NULL
);

CREATE TABLE dim_filiale (
    id_filiale        INT           AUTO_INCREMENT PRIMARY KEY,
    nom_filiale       VARCHAR(100)  NOT NULL UNIQUE,
    pays              CHAR(3)       NOT NULL,
    zone_geo          VARCHAR(50)   NOT NULL,
    devise_principale CHAR(3)       NOT NULL,
    seuil_alerte      DECIMAL(18,2) NOT NULL,
    FOREIGN KEY (devise_principale) REFERENCES dim_devise(code_devise)
);

CREATE TABLE dim_calendrier (
    date_id       INT       PRIMARY KEY,             -- AAAAMMJJ
    date          DATE      NOT NULL UNIQUE,
    jour          TINYINT   NOT NULL,
    mois          TINYINT   NOT NULL,
    annee         SMALLINT  NOT NULL,
    jour_semaine  TINYINT   NOT NULL,                -- 1 = lundi ... 7 = dimanche
    ouvre_fra     BOOLEAN   NOT NULL,                -- jour ouvré par pays
    ouvre_can     BOOLEAN   NOT NULL,
    ouvre_civ     BOOLEAN   NOT NULL,
    CHECK (jour BETWEEN 1 AND 31),
    CHECK (mois BETWEEN 1 AND 12)
);

CREATE TABLE dim_type_flux (
    id_type_flux  INT           AUTO_INCREMENT PRIMARY KEY,
    libelle       VARCHAR(100)  NOT NULL UNIQUE,
    sens          VARCHAR(20)   NOT NULL,
    CHECK (sens IN ('ENCAISSEMENT', 'DECAISSEMENT'))
);

-- ------------------------- FAITS REPORTING ---------------------------
CREATE TABLE fait_flux_tresorerie (
    id_flux       INT           AUTO_INCREMENT PRIMARY KEY,
    date_id       INT           NOT NULL,
    id_filiale    INT           NOT NULL,
    code_devise   CHAR(3)       NOT NULL,
    id_type_flux  INT           NOT NULL,
    montant       DECIMAL(18,2) NOT NULL,            -- devise d'origine, toujours positif
    montant_usd   DECIMAL(18,2) NOT NULL,            -- converti en devise de reporting
    statut        VARCHAR(20)   NOT NULL,
    CHECK (montant >= 0),
    CHECK (statut IN ('REALISE', 'PREVISIONNEL')),
    FOREIGN KEY (date_id)      REFERENCES dim_calendrier(date_id),
    FOREIGN KEY (id_filiale)   REFERENCES dim_filiale(id_filiale),
    FOREIGN KEY (code_devise)  REFERENCES dim_devise(code_devise),
    FOREIGN KEY (id_type_flux) REFERENCES dim_type_flux(id_type_flux),
    INDEX ix_flux_filiale_date (id_filiale, date_id, statut)
);

CREATE TABLE fait_taux (
    date_id          INT            NOT NULL,
    code_devise      CHAR(3)        NOT NULL,
    taux_change_usd  DECIMAL(18,10) NOT NULL,        -- valeur en USD d'une unité de devise
    taux_directeur   DECIMAL(6,3),                   -- % ; NULL pour l'USD (hors périmètre)
    PRIMARY KEY (date_id, code_devise),
    CHECK (taux_change_usd > 0),
    FOREIGN KEY (date_id)     REFERENCES dim_calendrier(date_id),
    FOREIGN KEY (code_devise) REFERENCES dim_devise(code_devise)
);

-- ------------------------- FAITS PREDICTIVE --------------------------
CREATE TABLE fait_prevision (
    id_prevision     INT           AUTO_INCREMENT PRIMARY KEY,
    type_run         VARCHAR(20)   NOT NULL,         -- BACKTEST (évaluation) / PRODUCTION
    date_generation  DATE          NOT NULL,
    date_cible       DATE          NOT NULL,
    id_filiale       INT           NOT NULL,
    code_devise      CHAR(3)       NOT NULL,
    modele           VARCHAR(20)   NOT NULL,
    montant_prevu    DECIMAL(18,2) NOT NULL,         -- flux net prévu (devise locale)
    borne_basse      DECIMAL(18,2) NOT NULL,         -- intervalle de confiance 80 %
    borne_haute      DECIMAL(18,2) NOT NULL,
    CHECK (type_run IN ('BACKTEST', 'PRODUCTION')),
    CHECK (modele IN ('PROPHET', 'ARIMA')),
    CHECK (date_cible > date_generation),
    CHECK (borne_basse <= montant_prevu AND montant_prevu <= borne_haute),
    FOREIGN KEY (date_cible)  REFERENCES dim_calendrier(date),
    FOREIGN KEY (id_filiale)  REFERENCES dim_filiale(id_filiale),
    FOREIGN KEY (code_devise) REFERENCES dim_devise(code_devise)
);

CREATE TABLE fait_prevision_taux (
    id_prevision_taux INT            AUTO_INCREMENT PRIMARY KEY,
    date_generation   DATE           NOT NULL,
    date_cible        DATE           NOT NULL,
    code_devise       CHAR(3)        NOT NULL,
    modele            VARCHAR(20)    NOT NULL,
    taux_prevu        DECIMAL(18,10) NOT NULL,
    borne_basse       DECIMAL(18,10) NOT NULL,
    borne_haute       DECIMAL(18,10) NOT NULL,
    CHECK (modele IN ('PROPHET', 'ARIMA')),
    FOREIGN KEY (date_cible)  REFERENCES dim_calendrier(date),
    FOREIGN KEY (code_devise) REFERENCES dim_devise(code_devise)
);

CREATE TABLE perf_modele (
    id_filiale          INT           NOT NULL,
    modele              VARCHAR(20)   NOT NULL,      -- PROPHET / ARIMA / MANUEL (méthode actuelle)
    date_generation     DATE          NOT NULL,
    nb_jours            INT           NOT NULL,
    mae                 DECIMAL(18,2) NOT NULL,      -- erreur absolue moyenne journalière
    wape_pct            DECIMAL(8,2)  NOT NULL,      -- erreur absolue pondérée (%)
    ecart_position_j30  DECIMAL(18,2) NOT NULL,      -- erreur sur la position à J+30
    retenu              BOOLEAN       NOT NULL,      -- meilleur modèle de la filiale
    PRIMARY KEY (id_filiale, modele),
    FOREIGN KEY (id_filiale) REFERENCES dim_filiale(id_filiale)
);

CREATE TABLE fait_scenario_stress (
    id_scenario            INT           AUTO_INCREMENT PRIMARY KEY,
    libelle_scenario       VARCHAR(100)  NOT NULL,
    date_cible             DATE          NOT NULL,
    id_filiale             INT           NOT NULL,
    code_devise            CHAR(3)       NOT NULL,
    type_choc              VARCHAR(50)   NOT NULL,
    valeur_choc            DECIMAL(8,2)  NOT NULL,   -- en % (ou points de % pour un taux)
    montant_base           DECIMAL(18,2) NOT NULL,   -- flux net prévu, USD
    montant_stresse        DECIMAL(18,2) NOT NULL,   -- flux net après choc, USD
    position_base_usd      DECIMAL(18,2) NOT NULL,
    position_stressee_usd  DECIMAL(18,2) NOT NULL,
    CHECK (valeur_choc <> 0),
    FOREIGN KEY (date_cible)  REFERENCES dim_calendrier(date),
    FOREIGN KEY (id_filiale)  REFERENCES dim_filiale(id_filiale),
    FOREIGN KEY (code_devise) REFERENCES dim_devise(code_devise)
);

-- ----------------------- SUIVI QUALITE ETL ---------------------------
CREATE TABLE etl_controle_qualite (
    id_controle      INT          AUTO_INCREMENT PRIMARY KEY,
    date_execution   DATETIME     NOT NULL,
    source           VARCHAR(100) NOT NULL,
    lignes_lues      INT          NOT NULL,
    doublons         INT          NOT NULL,
    non_pertinentes  INT          NOT NULL,
    rejets           INT          NOT NULL,
    lignes_chargees  INT          NOT NULL
);
