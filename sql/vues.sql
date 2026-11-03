-- =====================================================================
-- Vues de restitution pour Power BI (MOE §2.2.5)
-- =====================================================================
USE cresus_poc;

-- Flux net journalier par filiale et statut (devise locale et USD)
CREATE OR REPLACE VIEW v_flux_net_journalier AS
SELECT f.id_filiale, c.date, f.statut,
       SUM(CASE WHEN t.sens = 'ENCAISSEMENT' THEN f.montant     ELSE -f.montant     END) AS flux_net,
       SUM(CASE WHEN t.sens = 'ENCAISSEMENT' THEN f.montant_usd ELSE -f.montant_usd END) AS flux_net_usd
FROM fait_flux_tresorerie f
JOIN dim_calendrier c ON c.date_id = f.date_id
JOIN dim_type_flux  t ON t.id_type_flux = f.id_type_flux
GROUP BY f.id_filiale, c.date, f.statut;

-- Vue 1 « actifs » : position réalisée, valorisée en USD, avec alerte faible stock
CREATE OR REPLACE VIEW v_position_realisee AS
SELECT p.id_filiale, fi.nom_filiale, fi.devise_principale AS code_devise, p.date,
       p.flux_net, p.position,
       ROUND(p.position * tx.taux_change_usd, 2)    AS position_usd,
       fi.seuil_alerte,
       ROUND(fi.seuil_alerte * tx.taux_change_usd, 2) AS seuil_alerte_usd,
       CASE WHEN p.position < fi.seuil_alerte THEN 'ALERTE' ELSE 'OK' END AS statut_liquidite
FROM (SELECT id_filiale, date, flux_net,
             SUM(flux_net) OVER (PARTITION BY id_filiale ORDER BY date) AS position
      FROM v_flux_net_journalier WHERE statut = 'REALISE') p
JOIN dim_filiale    fi ON fi.id_filiale = p.id_filiale
JOIN dim_calendrier c  ON c.date = p.date
JOIN fait_taux      tx ON tx.date_id = c.date_id AND tx.code_devise = fi.devise_principale;

-- Position projetée à 30 jours : Prophet, ARIMA et prévision manuelle (MANUEL)
CREATE OR REPLACE VIEW v_position_projetee AS
WITH fin_histo AS (
    SELECT MAX(date) AS date_fin FROM v_flux_net_journalier WHERE statut = 'REALISE'
), depart AS (
    SELECT id_filiale, SUM(flux_net) AS position_depart
    FROM v_flux_net_journalier WHERE statut = 'REALISE' GROUP BY id_filiale
), spot AS (
    SELECT code_devise, taux_change_usd FROM fait_taux
    WHERE date_id = (SELECT MAX(date_id) FROM fait_taux)
), prev AS (
    SELECT id_filiale, date_cible AS date, modele, montant_prevu AS flux_net, borne_basse, borne_haute
    FROM fait_prevision WHERE type_run = 'PRODUCTION'
    UNION ALL
    SELECT id_filiale, date, 'MANUEL', flux_net, NULL, NULL
    FROM v_flux_net_journalier WHERE statut = 'PREVISIONNEL' AND date > (SELECT date_fin FROM fin_histo)
), cumul AS (
    SELECT p.*, d.position_depart + SUM(p.flux_net) OVER (PARTITION BY p.id_filiale, p.modele ORDER BY p.date)
               AS position_projetee
    FROM prev p JOIN depart d ON d.id_filiale = p.id_filiale
)
SELECT c.id_filiale, fi.nom_filiale, fi.devise_principale AS code_devise, c.date, c.modele,
       COALESCE(m.retenu, 0) AS modele_retenu,
       c.flux_net, c.borne_basse, c.borne_haute, c.position_projetee,
       ROUND(c.position_projetee * s.taux_change_usd, 2) AS position_projetee_usd,
       fi.seuil_alerte,
       CASE WHEN c.position_projetee < fi.seuil_alerte THEN 'ALERTE' ELSE 'OK' END AS statut_liquidite
FROM cumul c
JOIN dim_filiale fi ON fi.id_filiale = c.id_filiale
JOIN spot s ON s.code_devise = fi.devise_principale
LEFT JOIN perf_modele m ON m.id_filiale = c.id_filiale AND m.modele = c.modele;

-- Backtest : réalisé vs prévisions sur les 30 derniers jours (mesure du gain)
CREATE OR REPLACE VIEW v_backtest AS
SELECT p.id_filiale, fi.nom_filiale, p.date_cible AS date, p.modele,
       p.montant_prevu AS flux_prevu, COALESCE(r.flux_net, 0) AS flux_reel
FROM fait_prevision p
JOIN dim_filiale fi ON fi.id_filiale = p.id_filiale
LEFT JOIN v_flux_net_journalier r
       ON r.id_filiale = p.id_filiale AND r.date = p.date_cible AND r.statut = 'REALISE'
WHERE p.type_run = 'BACKTEST'
UNION ALL
SELECT m.id_filiale, fi.nom_filiale, m.date, 'MANUEL', m.flux_net, COALESCE(r.flux_net, 0)
FROM v_flux_net_journalier m
JOIN dim_filiale fi ON fi.id_filiale = m.id_filiale
LEFT JOIN v_flux_net_journalier r
       ON r.id_filiale = m.id_filiale AND r.date = m.date AND r.statut = 'REALISE'
WHERE m.statut = 'PREVISIONNEL'
  AND m.date <= (SELECT MAX(date) FROM v_flux_net_journalier WHERE statut = 'REALISE');

-- Vue 2 « devises » : projection du cours à J+30 et indicateur favorable / défavorable
-- (point de vue Groupe en USD : une devise locale qui s'apprécie valorise les positions)
CREATE OR REPLACE VIEW v_projection_taux AS
WITH spot AS (
    SELECT code_devise, taux_change_usd AS taux_spot FROM fait_taux
    WHERE date_id = (SELECT MAX(date_id) FROM fait_taux)
), j30 AS (
    SELECT code_devise, modele, taux_prevu, borne_basse, borne_haute FROM fait_prevision_taux
    WHERE date_cible = (SELECT MAX(date_cible) FROM fait_prevision_taux)
)
SELECT j.code_devise, d.libelle_devise, j.modele, s.taux_spot,
       j.taux_prevu AS taux_prevu_j30, j.borne_basse, j.borne_haute,
       ROUND((j.taux_prevu / s.taux_spot - 1) * 100, 3) AS variation_pct,
       CASE WHEN j.taux_prevu / s.taux_spot - 1 >  0.005 THEN 'FAVORABLE'
            WHEN j.taux_prevu / s.taux_spot - 1 < -0.005 THEN 'DEFAVORABLE'
            ELSE 'NEUTRE' END AS indicateur
FROM j30 j
JOIN spot s USING (code_devise)
JOIN dim_devise d USING (code_devise);

-- Synthèse des scénarios de stress à J+30
CREATE OR REPLACE VIEW v_stress_synthese AS
WITH spot AS (
    SELECT code_devise, taux_change_usd FROM fait_taux
    WHERE date_id = (SELECT MAX(date_id) FROM fait_taux)
)
SELECT s.libelle_scenario, s.type_choc, s.valeur_choc, s.id_filiale, fi.nom_filiale,
       MAX(CASE WHEN s.date_cible = x.date_max THEN s.position_base_usd END)     AS position_base_j30_usd,
       MAX(CASE WHEN s.date_cible = x.date_max THEN s.position_stressee_usd END) AS position_stressee_j30_usd,
       MAX(CASE WHEN s.date_cible = x.date_max THEN s.position_stressee_usd - s.position_base_usd END)
                                                                                 AS impact_usd,
       MIN(s.position_stressee_usd)                                             AS position_min_usd,
       ROUND(fi.seuil_alerte * sp.taux_change_usd, 2)                           AS seuil_alerte_usd,
       -- un choc de change dévalue position ET seuil (la liquidité locale est inchangée)
       SUM(s.position_stressee_usd < fi.seuil_alerte * sp.taux_change_usd
           * CASE WHEN s.type_choc = 'TAUX_CHANGE' THEN 1 + s.valeur_choc / 100 ELSE 1 END)
                                                                                 AS nb_jours_sous_seuil
FROM fait_scenario_stress s
JOIN dim_filiale fi ON fi.id_filiale = s.id_filiale
JOIN spot sp ON sp.code_devise = fi.devise_principale
CROSS JOIN (SELECT MAX(date_cible) AS date_max FROM fait_scenario_stress) x
GROUP BY s.libelle_scenario, s.type_choc, s.valeur_choc, s.id_filiale, fi.nom_filiale,
         fi.seuil_alerte, sp.taux_change_usd;
