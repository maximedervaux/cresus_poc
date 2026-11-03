# Restitution Power BI – POC Crésus

## Projet PBIP livré — Windows, 3 novembre 2026

Ouvrir `powerbi/Cresus.pbip` dans Power BI Desktop. Les sources sont **MySQL en Import**, actualisables ; il ne s'agit pas de DirectQuery ni de temps réel. Projet texte : `Cresus.SemanticModel/definition/` (TMDL) et `Cresus.Report/definition/` (PBIR).

Avant l'ouverture, si votre version le demande : Options → Fonctionnalités en préversion → activer l'enregistrement PBIP, TMDL et le format de rapport PBIR, puis redémarrer Desktop. La version Store est présente sur ce PC ; son numéro et ces options n'ont pas pu être inspectés par l'automatisation.

### État réellement vérifié

- Git et Python 3.13.2 présents. `.venv` créée, dépendances exactes de `requirements.txt` installées ; aucune logique Python modifiée.
- MySQL Community 8.4.13 déployé localement hors dépôt et démarré pour les contrôles sur `127.0.0.1:3306`. **Instance de test lancée en processus, pas encore un service Windows permanent.** Son répertoire est `C:\Users\lucas\Documents\Codex\2026-11-03\j\work\mysql-data`.
- ETL exécuté : 13 142 flux, 2 920 taux, 791 dates. Par source : 22 doublons, 13 lignes non pertinentes, 9 rejets.
- Prophet bloqué par Windows, erreur native 623 (« repositionnement de DLL système non autorisé »). **La pipeline complète n'est pas validée.** Les quatre tables prédictives initialement vides ont été remplies à partir des exports fournis : fait_prevision (360), fait_prevision_taux (180), perf_modele (9), fait_scenario_stress (360). Les vues ont ensuite été créées depuis `sql/vues.sql`. Ce sont les résultats préexistants du POC, pas des prévisions recalculées sur ce PC.
- Contrôles MySQL : MAE retenue FR ARIMA 7 413 939,92 EUR ; CA Prophet 3 690 352,40 CAD ; CI Prophet 721 311 236,24 XAF. Retrait massif, CI : 22 jours sous seuil. Lecture du compte `powerbi` vérifiée, avec GRANT SELECT uniquement sur la base.
- Modèle chargé par le désérialiseur TMDL Microsoft : 18 tables, 23 relations, 20 mesures. Les 33 fichiers JSON/PBIP/PBISM/PBIR passent les schémas officiels Microsoft.
- **Ouverture, calcul DAX, exécution Power Query et rendu des visuels dans Desktop restent à valider.** Le contrôle Windows renvoie la mauvaise fenêtre et l'ouverture depuis le processus restreint échoue avec accès refusé.
- Connector/NET 9.7.0 officiel téléchargé, signature Oracle valide. Installation refusée par Windows Installer (1601, accès au service refusé). Installation administrative nécessaire ; aucune réinstallation de Power BI n'est utile.

### Première actualisation et secours CSV

1. Terminer l'installation de Connector/NET, vérifier que le serveur MySQL est démarré et redémarrer Desktop.
2. Ouvrir `Cresus.pbip`. Paramètres Power Query : `ServeurMySQL=localhost:3306`, `BaseMySQL=cresus_poc`, `ModeSource=MySQL`.
3. Actualiser. Choisir l'authentification **Base de données**, utilisateur `powerbi`, et saisir le mot de passe défini localement. Aucun mot de passe n'est inclus dans les fichiers livrés ou versionnables.
4. Si MySQL ou le connecteur est indisponible : Transformer les données → Gérer les paramètres → `ModeSource=CSV`, `DossierExports=C:\Projet_BI\cresus_poc\exports`. Appliquer puis actualiser. Chaque objet conserve ses types et ses mesures ; UTF-8, virgule, culture `en-US`, dates explicites. Remettre `ModeSource=MySQL` pour revenir à la base.
5. Les données financières simulées du POC s'arrêtent au 31/10/2026 et les projections au 30/11/2026. Une nouvelle exécution de la pipeline **recrée la base** et efface le snapshot prédictif avant de recalculer : attendre la résolution de l'erreur Prophet avant de relancer.

### Modèle et écarts délibérés au guide

Les 16 objets demandés sont présents avec une partition Import chacun ; la requête M utilise `MySQL.Database(ServeurMySQL, BaseMySQL, [ReturnSingleDatabase=true])` et navigue par Schema/Item. Dates typées, montants en décimal fixe, taux en double, indicateurs 0/1 en entier. `dim_calendrier` : catégorie Time et colonne date déclarée clé (table de dates). Relations à sens unique, sans liaison filiale → devise, pour éviter les chemins ambigus. Ajout des liens calendrier sur les vues temporelles et faits de taux/stress, et devise sur v_projection_taux.

Table `_Mesures` dédiée ; table `_Scenarios` commune aux détails et à la synthèse pour qu'un seul segment filtre les deux. Un scénario doit être sélectionné pour afficher les mesures de stress ; les positions de plusieurs scénarios ne doivent pas être additionnées. Les jours sous seuil agrégés sur plusieurs filiales sont des **jours-filiale** (sélectionner CI pour contrôler 22 jours).

Les montants USD s'affichent en millions. Les montants locaux des tables de performance restent dans leur devise d'origine. Gain manuel et MAE restent vides sans filiale unique : mélanger EUR, CAD et XAF serait trompeur. Le flux net réalisé est filtré sur REALISE, contrairement à la formule initiale du guide qui incluait PREVISIONNEL. Les BOOLEAN sont filtrés avec `= 1`.

### Pages et finitions manuelles déclarées

22 visuels natifs sont fournis sur cinq pages, avec segments, cartes, graphiques et tableaux. Cette première version privilégie les visuels simples autorisés par le cahier des charges.

- Actifs & liquidité : cartes, histogramme position/seuil en USD, courbe réalisé/projection retenue en USD, tableau stocks **de toutes les filiales**, écart au seuil. À finir : tri croissant et filtre écart < 0 pour la liste des seules alertes ; format conditionnel rouge via la mesure Couleur alerte. Le passage en USD rend la courbe consolidable ; les montants locaux restent disponibles dans les vues.
- Projection des devises : choisir **une devise et un modèle** ; courbe prévision et deux bornes. Tableau spot/J+30/variation/indicateur. À finir : bande de confiance ombrée et icônes vert/rouge/gris. `variation_pct` est déjà exprimée en points de %, ne pas appliquer un format pourcentage multipliant par 100 ; même règle pour wape_pct.
- Fiabilité : choisir **une filiale et un modèle** dans les segments pour le réel/prévu. La carte gain compare le modèle retenu au manuel pour la filiale, indépendamment du segment modèle du backtest. Tableau perf_modele disponible. À finir si nécessaire : petits multiples par modèle.
- Stress : choisir **un scénario**, puis éventuellement une filiale ; positions base/stress, impact J+30, tableau jours sous seuil. À finir : ligne de seuil dynamique (pour les chocs de change, ajuster aussi le seuil avec la dépréciation conformément à sql/vues.sql).
- Qualité : tableau des contrôles par source/date.

### Reproduction et revue

`powerbi/tools/generer_projet.py` régénère les fichiers initiaux depuis les en-têtes des CSV ; il écrase les fichiers générés. Ne pas le relancer sur une mise en page retouchée dans Desktop sans sauvegarde. `powerbi/tools/valider_json.py` exige jsonschema et un accès HTTPS aux schémas Microsoft. Les fichiers `.pbi/localSettings.json`, `.pbi/cache.abf` et `.pbi/unappliedChanges.json` sont exclus de Git.

Aucun commit/push effectué. Examiner le diff avant de confirmer le commit et le push sur main.

Références : [structure PBIR Microsoft](https://learn.microsoft.com/power-bi/developer/projects/projects-report), [TMDL Microsoft](https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview), [MySQL pour Windows](https://dev.mysql.com/doc/refman/8.4/en/windows-installation.html).

---

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
VAR mae_modele = CALCULATE ( AVERAGE ( perf_modele[mae] ), perf_modele[retenu] = 1 )
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
