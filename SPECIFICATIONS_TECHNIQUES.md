# Spécifications techniques — POC Crésus

## 1. Objet et périmètre

Le POC met en œuvre une chaîne de Business Intelligence de trésorerie pour trois filiales :

| Filiale | Pays | Devise implémentée | Devise à confirmer/corriger |
|---|---|---|---|
| ZF_BANQUE_FRANCE | FRA | EUR | EUR |
| ZF_BANQUE_CANADA | CAN | CAD | CAD |
| ZF_BANQUE_COTE_IVOIRE | CIV | XAF | **XOF** (devise réelle de la Côte d’Ivoire) |

Le périmètre comprend l’intégration des flux de trésorerie et données de marché, leur mise en forme dans une base MySQL, des prévisions et scénarios de stress calculés en Python, puis une restitution Power BI.

Les flux des filiales sont des données synthétiques générées de façon reproductible ; ils ne sont pas des extractions bancaires réelles. Les cours EUR/USD et EUR/CAD sont extraits de Frankfurter (données de référence BCE). Le cours XAF est construit à partir de la parité fixe EUR/XAF définie dans le code. Les taux directeurs sont saisis manuellement à titre indicatif. Ces limites doivent être rappelées pendant la démonstration et dans l’interprétation des résultats.

## 2. Architecture et flux de données

```text
Systèmes simulés des filiales ─┐
Frankfurter / cours de change ─┼─> fichiers CSV (data/sources)
Taux directeurs / jours fériés ┘
                                  |
                                  v
                         ETL Python (etl.py)
                                  |
                 +----------------+----------------+
                 v                                 v
        Zone ODS / staging                 Zone DWH / reporting
        tables stg_*                       dimensions dim_*
        données sources                    faits fait_flux_tresorerie,
        chargées sans typage métier         fait_taux
                 |                                 |
                 +---------------+-----------------+
                                 v
                   Zone prédictive (Python)
                   fait_prevision, fait_prevision_taux,
                   perf_modele, fait_scenario_stress
                                 |
                                 v
                      vues SQL v_* et exports CSV
                                 |
                                 v
                         Power BI (Import)
```

Les zones ODS, DWH et prédictive sont des groupes de tables dans la base `cresus_poc`, distingués par des préfixes ; ce ne sont pas des bases ou schémas MySQL séparés. Les tables `stg_*` sont créées dynamiquement à partir des colonnes des fichiers CSV et rechargées par l’ETL.

### Étapes de traitement

1. `extract_marche.py` récupère les cours disponibles et génère les CSV de marché ; `generer_flux_filiales.py` produit les trois fichiers de flux simulés et les données de jours fériés.
2. `etl.py` lit les fichiers, charge les tables staging, standardise les données, supprime les doublons, filtre les lignes identifiées comme non pertinentes, rejette les lignes invalides, convertit les montants en USD et charge les dimensions et faits de reporting.
3. `prediction.py` calcule le backtest et la prévision de production à 30 jours avec Prophet et ARIMA, ainsi que les projections de change. Les résultats alimentent les tables prédictives.
4. `stress.py` applique quatre scénarios aux prévisions retenues et charge les résultats de stress.
5. `restitution.py` prépare les vues SQL et les fichiers d’export consommés par Power BI.

**Attention exploitation :** `sql/schema.sql` commence par `DROP DATABASE IF EXISTS cresus_poc`. L’ETL recrée donc la base et détruit son contenu précédent à chaque exécution. Cette stratégie est acceptable pour le POC reproductible, mais pas pour une exploitation conservant l’historique.

## 3. Sources de données

| Source | Fichier / origine | Format et colonnes | Traitement / limites |
|---|---|---|---|
| Flux France | `flux_tresorerie_FR.csv`, généré par `generer_flux_filiales.py` | CSV `;`, CP1252 : `Date_Operation`, `Libelle`, `Montant`, `Devise`, `Statut` | Date `JJ/MM/AAAA`, séparateur décimal virgule, libellés français. Les lignes annulées sont filtrées. Synthétique. |
| Flux Canada | `flux_tresorerie_CA.csv`, généré par `generer_flux_filiales.py` | CSV `,` : `txn_date`, `category`, `amount`, `currency`, `status` | Date `MM/JJ/AAAA`, catégories anglaises, montants de décaissement signés à la source. Transfert interne filtré. Synthétique. |
| Flux Côte d’Ivoire | `flux_tresorerie_CI.csv`, généré par `generer_flux_filiales.py` | CSV `|` : `DATE_VALEUR`, `NATURE_FLUX`, `SENS`, `MONTANT_XAF`, `ETAT` | Date `AAAAMMJJ`, codes de flux, montants avec espaces de milliers ; cohérence du sens `C/D` contrôlée. Synthétique et actuellement libellé XAF dans le POC ; à corriger en XOF avant de présenter cette devise comme réelle. |
| Cours de change | `taux_change.csv`, API Frankfurter | `date`, `devise_base`, `devise_cotee`, `taux` | Cotations CAD et XAF par rapport à EUR. Le cours EUR/XAF est une parité fixe ajoutée par le générateur, non une cotation API. |
| Valeur USD | `valeur_usd.csv`, API Frankfurter | `date`, `eur_usd` | Valeur en USD d’un EUR ; combinée aux cours EUR/devise pour obtenir la valeur USD d’une unité de devise locale. |
| Taux directeurs | `taux_directeurs.csv`, saisie dans `extract_marche.py` | `date_effet`, `code_devise`, `banque_centrale`, `taux_pct` | Valeurs manuelles indicatives, propagées jusqu’à la prochaine date d’effet. Ce n’est pas une source automatique de banques centrales. |
| Jours fériés | `calendrier_jours_feries.csv`, généré avec les calendriers pays | `date`, `pays`, `libelle` | Utilisé pour déterminer les jours ouvrés FRA, CAN et CIV. |

Fenêtre prévue dans la configuration : historique du 1er novembre 2024 au 31 octobre 2026 ; horizon de prévision de 30 jours ; calendrier jusqu’au 31 décembre 2026.

## 4. Normes de nommage

Les conventions effectivement appliquées dans le projet sont :

| Élément | Convention | Exemples |
|---|---|---|
| Tables de staging | Préfixe `stg_`, nom source en minuscules | `stg_flux_fr`, `stg_taux_change` |
| Dimensions | Préfixe `dim_`, nom métier au singulier | `dim_calendrier`, `dim_filiale` |
| Tables de faits | Préfixe `fait_`, nom métier | `fait_flux_tresorerie`, `fait_prevision` |
| Vues de restitution | Préfixe `v_`, nom descriptif | `v_position_realisee`, `v_backtest` |
| Colonnes | `snake_case`, noms français explicites | `date_generation`, `montant_usd` |
| Identifiants | Préfixe `id_` pour les clés numériques ; code métier pour certains référentiels | `id_filiale`, `code_devise`, `date_id` |
| Unités et périodes | Suffixe explicite lorsqu’utile | `_usd`, `_pct`, `_j30` |
| Valeurs catégorielles | Codes majuscules stables | `REALISE`, `PRODUCTION`, `ENCAISSEMENT`, `PROPHET` |

Les montants des flux sont positifs dans le fait ; le sens économique provient de `dim_type_flux.sens`. Les montants locaux et USD sont séparés dans des colonnes distinctes. Les prévisions de flux et les taux de change sont des faits distincts.

## 5. Modèle dimensionnel DWH

### Modèle en étoile de reporting

```text
dim_calendrier ─────┬── fait_flux_tresorerie ──┬── dim_filiale
                    │                           ├── dim_devise
                    │                           └── dim_type_flux
                    └── fait_taux ───────────────── dim_devise
```

| Table | Grain | Clé primaire | Relations principales |
|---|---|---|---|
| `dim_calendrier` | Un jour | `date_id` (`AAAAMMJJ`) | Référencée par les faits via `date_id` ou `date`. |
| `dim_filiale` | Une filiale | `id_filiale` | Référence `dim_devise` par `devise_principale`. |
| `dim_devise` | Une devise | `code_devise` | Référencée par les faits de flux et de taux. |
| `dim_type_flux` | Un type de flux | `id_type_flux` | Référencée par `fait_flux_tresorerie`. Porte le sens économique. |
| `fait_flux_tresorerie` | Un flux source normalisé | `id_flux` | Clés vers calendrier, filiale, devise et type de flux. |
| `fait_taux` | Un cours et une devise par jour | (`date_id`, `code_devise`) | Clés vers calendrier et devise. |

`dim_calendrier` contient les attributs de date, le jour de semaine et les indicateurs de jours ouvrés `ouvre_fra`, `ouvre_can`, `ouvre_civ`. La modélisation Power BI ajoute les relations temporelles et les faits prédictifs ; les relations sont unidirectionnelles pour limiter les chemins ambigus.

### Tables prédictives et de qualité

Ces tables complètent le DWH pour l’analyse prédictive ; elles ne sont pas toutes des faits du modèle en étoile de reporting.

| Table | Grain / contenu |
|---|---|
| `fait_prevision` | Une prévision de flux par type de run, date cible, filiale et modèle. `BACKTEST` sert à l’évaluation ; `PRODUCTION` à la projection opérationnelle. |
| `fait_prevision_taux` | Une prévision de taux par date cible, devise et modèle. |
| `perf_modele` | Performance par filiale et modèle, avec sélection du modèle retenu. |
| `fait_scenario_stress` | Une ligne par scénario, date cible et filiale, avec valeurs de base et stressées en USD. |
| `etl_controle_qualite` | Compteurs de contrôle par exécution et source. |

### Dictionnaire de données

Les types ci-dessous sont ceux déclarés dans `sql/schema.sql`. Les tables staging sont dynamiques : elles reprennent les en-têtes sources et ajoutent `date_chargement` ; leurs types physiques sont inférés par Pandas/SQLAlchemy et ne constituent pas un contrat typé stable.

#### Dimensions

| Table | Colonne | Type | Description |
|---|---|---|---|
| `dim_devise` | `code_devise` | `CHAR(3)` | Code devise, clé primaire. |
|  | `libelle_devise` | `VARCHAR(50)` | Libellé de la devise. |
| `dim_filiale` | `id_filiale` | `INT` | Identifiant technique, clé primaire. |
|  | `nom_filiale` | `VARCHAR(100)` | Nom unique de la filiale. |
|  | `pays` | `CHAR(3)` | Code pays utilisé par le calendrier (`FRA`, `CAN`, `CIV`). |
|  | `zone_geo` | `VARCHAR(50)` | Zone géographique. |
|  | `devise_principale` | `CHAR(3)` | Devise locale, clé étrangère vers `dim_devise`. |
|  | `seuil_alerte` | `DECIMAL(18,2)` | Seuil de position de liquidité en devise locale. |
| `dim_calendrier` | `date_id` | `INT` | Clé `AAAAMMJJ`. |
|  | `date` | `DATE` | Date calendaire unique. |
|  | `jour`, `mois` | `TINYINT` | Jour du mois et numéro de mois. |
|  | `annee` | `SMALLINT` | Année. |
|  | `jour_semaine` | `TINYINT` | Jour de semaine, lundi = 1 à dimanche = 7. |
|  | `ouvre_fra`, `ouvre_can`, `ouvre_civ` | `BOOLEAN` | Indique si le jour est ouvré pour le pays correspondant. |
| `dim_type_flux` | `id_type_flux` | `INT` | Identifiant technique, clé primaire. |
|  | `libelle` | `VARCHAR(100)` | Code métier du flux, unique (ex. `DEPOTS_CLIENTS`). |
|  | `sens` | `VARCHAR(20)` | `ENCAISSEMENT` ou `DECAISSEMENT`. |

#### Faits de reporting

| Table | Colonne | Type | Description |
|---|---|---|---|
| `fait_flux_tresorerie` | `id_flux` | `INT` | Identifiant technique du flux. |
|  | `date_id`, `id_filiale`, `code_devise`, `id_type_flux` | `INT`, `INT`, `CHAR(3)`, `INT` | Clés vers calendrier, filiale, devise et type de flux. |
|  | `montant` | `DECIMAL(18,2)` | Montant absolu dans la devise d’origine. |
|  | `montant_usd` | `DECIMAL(18,2)` | Montant converti en USD au cours applicable. |
|  | `statut` | `VARCHAR(20)` | `REALISE` ou `PREVISIONNEL`. |
| `fait_taux` | `date_id`, `code_devise` | `INT`, `CHAR(3)` | Clé composite jour/devise. |
|  | `taux_change_usd` | `DECIMAL(18,10)` | USD pour une unité de devise locale. |
|  | `taux_directeur` | `DECIMAL(6,3)` | Taux directeur en pourcentage ; NULL pour USD. |

#### Faits prédictifs et suivi

| Table | Colonnes | Description |
|---|---|---|
| `fait_prevision` | `id_prevision`, `type_run`, `date_generation`, `date_cible`, `id_filiale`, `code_devise`, `modele`, `montant_prevu`, `borne_basse`, `borne_haute` | Flux net journalier prévu en devise locale, avec intervalle de confiance à 80 %. `modele` vaut `PROPHET` ou `ARIMA`. |
| `fait_prevision_taux` | `id_prevision_taux`, `date_generation`, `date_cible`, `code_devise`, `modele`, `taux_prevu`, `borne_basse`, `borne_haute` | Projection du taux USD par unité de devise, avec intervalle de prévision. |
| `perf_modele` | `id_filiale`, `modele`, `date_generation`, `nb_jours`, `mae`, `wape_pct`, `ecart_position_j30`, `retenu` | Mesures du backtest et indicateur du modèle retenu. `MANUEL` correspond à la référence des trésoriers simulée. |
| `fait_scenario_stress` | `id_scenario`, `libelle_scenario`, `date_cible`, `id_filiale`, `code_devise`, `type_choc`, `valeur_choc`, `montant_base`, `montant_stresse`, `position_base_usd`, `position_stressee_usd` | Flux et positions de base/stress en USD ; `valeur_choc` représente un pourcentage ou des points de taux selon le type de choc. |
| `etl_controle_qualite` | `id_controle`, `date_execution`, `source`, `lignes_lues`, `doublons`, `non_pertinentes`, `rejets`, `lignes_chargees` | Traçabilité agrégée des contrôles de chargement ETL. |

## 6. Mapping des données sources vers le DWH

| Source / champ | Transformation | Cible |
|---|---|---|
| France `Date_Operation` | Conversion du format `JJ/MM/AAAA` en date | `dim_calendrier.date`, puis `fait_flux_tresorerie.date_id` |
| Canada `txn_date` | Conversion du format `MM/JJ/AAAA` en date | `dim_calendrier.date`, puis `fait_flux_tresorerie.date_id` |
| CI `DATE_VALEUR` | Conversion du format `AAAAMMJJ` en date | `dim_calendrier.date`, puis `fait_flux_tresorerie.date_id` |
| France `Libelle` | Correspondance par `LIB_FR` vers le code métier du référentiel | `dim_type_flux.libelle`, puis `fait_flux_tresorerie.id_type_flux` |
| Canada `category` | Suppression des espaces, passage en minuscules, correspondance `LIB_CA` | `dim_type_flux.libelle`, puis `fait_flux_tresorerie.id_type_flux` |
| CI `NATURE_FLUX` | Correspondance code court via `CODE_CI` ; validation avec le sens déclaré | `dim_type_flux.libelle`, puis `fait_flux_tresorerie.id_type_flux` |
| CI `SENS` | `C` → encaissement, `D` → décaissement ; ligne rejetée si incohérent avec le référentiel | Validation de `dim_type_flux.sens` |
| Flux France `Montant` | Virgule décimale convertie en nombre ; valeur absolue conservée | `fait_flux_tresorerie.montant` |
| Flux Canada `amount` | Conversion numérique puis valeur absolue ; le sens signé à la source n’est pas conservé comme signe métier | `fait_flux_tresorerie.montant` et sens via `dim_type_flux` |
| CI `MONTANT_XAF` | Espaces de milliers supprimés, conversion numérique | `fait_flux_tresorerie.montant` |
| France `Devise`, Canada `currency`, devise CI fixée à XAF | Normalisation en majuscules ; référence au référentiel devise | `dim_devise.code_devise`, `fait_flux_tresorerie.code_devise` |
| France `Statut`, Canada `status`, CI `ETAT` | `Réalisé`/`Actual`/`R` → `REALISE` ; `Prévisionnel`/`Forecast`/`P` → `PREVISIONNEL` | `fait_flux_tresorerie.statut` |
| Référentiel filiales dans `config.py` | Identifiant, nom, pays, région, devise principale et seuil d’alerte | `dim_filiale` |
| `calendrier_jours_feries.csv` | Calendrier quotidien ; week-ends et jours fériés retirés des jours ouvrés | `dim_calendrier` |
| `taux_change.csv` + `valeur_usd.csv` | EUR = `eur_usd` ; CAD = `eur_usd / taux_EUR_CAD` ; XAF = `eur_usd / taux_EUR_XAF` ; USD = 1. Dernier cours connu propagé aux jours sans cotation. | `fait_taux.taux_change_usd` |
| `taux_directeurs.csv` | Taux d’effet le plus récent propagé vers l’avant par devise | `fait_taux.taux_directeur` |
| `montant` + cours applicable de la date/devise | Conversion `montant_usd = montant × taux_change_usd` | `fait_flux_tresorerie.montant_usd` |

Toutes les sources de flux sont dédoublonnées sur les lignes identiques. Sont filtrées : opérations annulées en France, transferts internes au Canada et lignes `TEST` en CI. Les lignes invalides ou incomplètes sont comptabilisées comme rejets. L’ETL met le montant au positif ; l’encaissement/décaissement est ensuite appliqué dans les vues et calculs à l’aide du référentiel de types de flux.

## 7. Restitution, vues et KPI

Le projet Power BI est livré dans `powerbi/Cresus.pbip`. Le modèle utilise les tables et vues MySQL en mode **Import** ; des exports CSV existent également dans `exports/` comme solution de repli. La connexion et les paramètres sont décrits dans `powerbi/GUIDE_POWERBI.md`.

| Vue / objet | Contenu |
|---|---|
| `v_flux_net_journalier` | Flux nets quotidiens par filiale, date et statut, en monnaie locale et USD. |
| `v_position_realisee` | Position réalisée cumulée, valorisation USD, seuil et statut de liquidité. |
| `v_position_projetee` | Position projetée à 30 jours par modèle, dont le modèle retenu et la référence manuelle. |
| `v_backtest` | Flux réels comparés aux prévisions Prophet, ARIMA et manuelles. |
| `v_projection_taux` | Cours spot, projection J+30, variation et indicateur favorable/défavorable/neutre. |
| `v_stress_synthese` | Impact des scénarios, position minimum et jours sous seuil. |

| KPI | Définition |
|---|---|
| Position actuelle USD | Dernière position réalisée disponible, convertie en USD et agrégée selon le filtre filiale. |
| Devises en alerte | Nombre de filiales sous leur seuil de liquidité à la dernière date réalisée. |
| Position J+30 USD (modèle retenu) | Position projetée à la dernière date de projection pour le modèle retenu au backtest. |
| Flux net réalisé USD | Somme des encaissements moins les décaissements réalisés, convertis en USD. |
| MAE backtest | Moyenne des valeurs absolues `flux prévu - flux réel` sur la période de backtest ; à analyser par filiale, car les devises locales diffèrent. |
| Gain vs prévision manuelle | `(MAE manuel - MAE modèle retenu) / MAE manuel`. Un résultat positif indique une réduction d’erreur. |
| Impact stress USD | Différence de position stressée et de position de base à J+30. Un scénario doit être sélectionné ; ne pas sommer plusieurs scénarios comme s’ils étaient additifs. |
| Jours sous seuil (stress) | Nombre de dates sous seuil dans le scénario. Une agrégation de plusieurs filiales correspond à des jours-filiale. |
| Contrôles qualité ETL | Lignes lues, doublons, lignes non pertinentes, rejets et lignes chargées par source et exécution. |

Les mesures de performance en devise locale ne doivent pas être comparées entre EUR, CAD et XAF/XOF sans conversion préalable. Le guide de restitution précise les filtres nécessaires pour éviter les agrégations trompeuses.

## 8. Exécution et prérequis

- Python et dépendances listées dans `requirements.txt`.
- MySQL 8+, base accessible via `CRESUS_DB_SERVER` (configuration par défaut : serveur local).
- Exécution complète : `python run_pipeline.py`.
- Réutilisation des fichiers sources : `python run_pipeline.py --sans-sources`.
- Power BI Desktop pour ouvrir `powerbi/Cresus.pbip` ; MySQL Connector/NET est nécessaire pour le connecteur MySQL.

La pipeline complète inclut des modèles Prophet et ARIMA. Le guide Power BI signale qu’une erreur native Prophet a empêché sa validation complète sur l’environnement Windows utilisé ; les données prédictives importées des exports ne doivent donc pas être présentées comme ayant été recalculées sur cet environnement. L’ouverture et le rendu dans Power BI Desktop doivent aussi être validés avant une démonstration live.

## 9. Écarts connus et actions avant livraison

1. **Devise Côte d’Ivoire :** le code et les données du POC utilisent XAF, alors que la devise de la Côte d’Ivoire est le XOF. Corriger le référentiel, les données, les transformations, les libellés et les éléments Power BI concernés avant de présenter les chiffres comme ceux de la Côte d’Ivoire. La parité commune avec l’euro ne rend pas les codes interchangeables.
2. **Sources simulées :** indiquer explicitement que les flux de filiales servent à valider la chaîne technique et non à démontrer une performance réelle.
3. **Taux directeurs :** remplacer la saisie manuelle indicative par une source officielle si une analyse réelle est attendue.
4. **Cycle de vie de la base :** remplacer la suppression/recréation de la base par une stratégie de migration et de chargement contrôlé en dehors du POC.
5. **Validation de la démo :** vérifier l’installation du connecteur, l’actualisation Power BI et le calcul des mesures DAX sur le poste de démonstration ; préparer une capture ou un enregistrement de secours.

## 10. Références du dépôt

- `config.py` — paramètres, filiales, devises et période.
- `generer_flux_filiales.py` — génération des sources synthétiques.
- `extract_marche.py` — extraction de marché et fichier de taux directeurs.
- `referentiels.py` — mapping des types de flux.
- `etl.py` — extraction, staging, transformations et chargement.
- `sql/schema.sql` et `sql/vues.sql` — schéma DWH et vues de restitution.
- `prediction.py` et `stress.py` — traitements prédictifs.
- `restitution.py` — préparation des vues et exports de restitution.
- `powerbi/GUIDE_POWERBI.md` — configuration et guide de démonstration Power BI.
