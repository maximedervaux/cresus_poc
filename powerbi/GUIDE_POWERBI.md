# Restitution Power BI – POC Crésus

> Power BI Desktop ne fonctionne que sous **Windows** (VM Parallels/UTM sur Mac, ou poste Windows).

## 1. Connexion aux données

**Connexion directe MySQL (MOE §2.1.4)**
1. Installer **MySQL Connector/NET** (requis par Power BI pour MySQL).
2. Power BI Desktop → *Obtenir les données* → *Base de données MySQL*.
3. Serveur : `<hôte>:3306`, base : `cresus_poc`. Mode **Import**.
4. Sélectionner les tables `dim_*`, `fait_*`, `perf_modele`, `etl_controle_qualite` et les vues `v_*`.

> Si MySQL tourne sur le Mac et Power BI dans une VM, il faut ouvrir MySQL au réseau
> (`bind-address`) et créer un utilisateur dédié en lecture seule :
> `CREATE USER 'powerbi'@'%' IDENTIFIED BY '...'; GRANT SELECT ON cresus_poc.* TO 'powerbi'@'%';`

## 2. Modèle (vue Modèle)

| De (N) | Vers (1) | Clé | Actif |
|---|---|---|---|
| fait_flux_tresorerie | dim_calendrier | date_id | oui |
| fait_flux_tresorerie | dim_filiale | id_filiale | oui |
| fait_flux_tresorerie | dim_devise | code_devise | oui |
| fait_flux_tresorerie | dim_type_flux | id_type_flux | oui |
| fait_taux | dim_calendrier | date_id | oui |
| fait_taux | dim_devise | code_devise | oui |
| fait_prevision | dim_calendrier | date_cible → date | oui |
| fait_prevision | dim_filiale | id_filiale | oui |
| fait_prevision_taux | dim_devise | code_devise | oui |
| fait_scenario_stress | dim_filiale | id_filiale | oui |
| v_position_realisee / v_position_projetee / v_backtest / v_stress_synthese / perf_modele | dim_filiale | id_filiale | oui |

Marquer `dim_calendrier` comme **table de dates** (colonne `date`).

## 3. Mesures DAX

```DAX
Position actuelle USD =
VAR d = MAX ( v_position_realisee[date] )
RETURN CALCULATE ( SUM ( v_position_realisee[position_usd] ), v_position_realisee[date] = d )

Devises en alerte =
VAR d = MAX ( v_position_realisee[date] )
RETURN CALCULATE ( COUNTROWS ( v_position_realisee ),
                   v_position_realisee[date] = d, v_position_realisee[statut_liquidite] = "ALERTE" )

Position J+30 USD (modèle retenu) =
VAR d = MAX ( v_position_projetee[date] )
RETURN CALCULATE ( SUM ( v_position_projetee[position_projetee_usd] ),
                   v_position_projetee[date] = d, v_position_projetee[modele_retenu] = 1 )

Flux net réalisé USD =
SUMX ( fait_flux_tresorerie,
       IF ( RELATED ( dim_type_flux[sens] ) = "ENCAISSEMENT", 1, -1 ) * fait_flux_tresorerie[montant_usd] )

MAE backtest = AVERAGEX ( v_backtest, ABS ( v_backtest[flux_prevu] - v_backtest[flux_reel] ) )

Gain vs prévision manuelle % =
VAR mae_modele = CALCULATE ( AVERAGE ( perf_modele[mae] ), perf_modele[retenu] = TRUE () )
VAR mae_manuel = CALCULATE ( AVERAGE ( perf_modele[mae] ), perf_modele[modele] = "MANUEL" )
RETURN DIVIDE ( mae_manuel - mae_modele, mae_manuel )

Impact stress USD = SUM ( v_stress_synthese[impact_usd] )

Jours sous seuil (stress) = SUM ( v_stress_synthese[nb_jours_sous_seuil] )
```

## 4. Pages du rapport

**Page 1 – Actifs & liquidité** (vue 1 du MOE §2.2.5)
- Cartes : *Position actuelle USD*, *Position J+30 USD (modèle retenu)*, *Devises en alerte*.
- Histogramme groupé : position par filiale vs `seuil_alerte_usd` (mise en forme conditionnelle rouge si `ALERTE`).
- Courbe : `v_position_realisee[position]` puis `v_position_projetee[position_projetee]` (légende `modele`), segment *filiale*.
- Tableau « devises à faible stock » : filiale, devise, position, seuil, écart au seuil, trié par écart croissant.

**Page 2 – Projection des devises** (vue 2 du MOE §2.2.5)
- Courbe `fait_prevision_taux[taux_prevu]` + bornes (bande de confiance 80 %), légende `modele`, segment devise.
- Tableau `v_projection_taux` : spot, J+30, `variation_pct`, `indicateur` avec icônes (▲ FAVORABLE vert, ▼ DÉFAVORABLE rouge, ● NEUTRE gris).

**Page 3 – Fiabilité des prévisions**
- Courbe `v_backtest` : `flux_reel` vs `flux_prevu` par `modele`, segment filiale.
- Tableau `perf_modele` (MAE, WAPE, écart position J+30) + carte *Gain vs prévision manuelle %*.

**Page 4 – Scénarios de stress**
- Segment `libelle_scenario`.
- Courbe `fait_scenario_stress` : `position_base_usd` vs `position_stressee_usd` par date, ligne constante = seuil.
- Histogramme `v_stress_synthese[impact_usd]` par filiale ; tableau des `nb_jours_sous_seuil`.

**Page 5 – Qualité des données**
- Tableau `etl_controle_qualite` : lignes lues / doublons / non pertinentes / rejets / chargées par source.

## 5. Actualisation
`run_pipeline.py` est planifié chaque jour (cron / Planificateur de tâches) ; Power BI est actualisé ensuite
(actualisation planifiée via une passerelle de données sur Power BI Service).
