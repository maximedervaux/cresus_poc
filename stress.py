"""Scénarios de stress appliqués à la prévision de production.

Pour chaque filiale, on part de la prévision du modèle retenu au backtest et de la
dernière position réalisée, puis on applique un choc paramétré :

  TAUX_CHANGE    : la devise locale perd valeur_choc % face à l'USD dès J+1
                   -> la position et les flux valent moins en devise de reporting.
  TAUX_DIRECTEUR : hausse de valeur_choc points du taux directeur
                   -> intérêts versés sur dépôts indexés à 100 %,
                      intérêts reçus indexés à 30 % (crédits majoritairement à taux fixe).
  RETRAIT_DEPOTS : les retraits clients augmentent de valeur_choc % chaque jour ouvré
                   (scénario de fuite des dépôts, logique LCR).

Les montants sont exprimés en USD au dernier cours connu (cours spot).
"""
import pandas as pd

from config import DATE_FIN_HISTO
from db import get_engine

SCENARIOS = [
    ("DEPRECIATION_DEVISE_10", "TAUX_CHANGE", -10),
    ("DEPRECIATION_DEVISE_20", "TAUX_CHANGE", -20),
    ("HAUSSE_TAUX_DIRECTEUR_200PB", "TAUX_DIRECTEUR", 2),
    ("RETRAIT_MASSIF_DEPOTS_30", "RETRAIT_DEPOTS", 30),
]
INDEXATION_INTERETS_RECUS = 0.30
FENETRE_MOYENNE_JOURS = 90


def charger(engine):
    filiales = pd.read_sql("SELECT * FROM dim_filiale", engine)
    prev = pd.read_sql("""
        SELECT p.id_filiale, p.date_cible, p.montant_prevu, c.ouvre_fra, c.ouvre_can, c.ouvre_civ
        FROM fait_prevision p
        JOIN perf_modele m ON m.id_filiale = p.id_filiale AND m.modele = p.modele AND m.retenu
        JOIN dim_calendrier c ON c.date = p.date_cible
        WHERE p.type_run = 'PRODUCTION' ORDER BY p.date_cible""", engine, parse_dates=["date_cible"])
    position = pd.read_sql("""
        SELECT f.id_filiale,
               SUM(CASE WHEN t.sens = 'ENCAISSEMENT' THEN f.montant ELSE -f.montant END) AS position
        FROM fait_flux_tresorerie f JOIN dim_type_flux t ON t.id_type_flux = f.id_type_flux
        WHERE f.statut = 'REALISE' GROUP BY f.id_filiale""", engine).set_index("id_filiale").position
    marche = pd.read_sql("""
        SELECT code_devise, taux_change_usd, taux_directeur FROM fait_taux
        WHERE date_id = (SELECT MAX(date_id) FROM fait_taux)""", engine).set_index("code_devise")
    # Moyenne par jour ouvré des flux sensibles aux chocs, sur les 90 derniers jours
    moyennes = pd.read_sql(f"""
        SELECT f.id_filiale, t.libelle, SUM(f.montant) / COUNT(DISTINCT f.date_id) AS moyenne
        FROM fait_flux_tresorerie f
        JOIN dim_type_flux t ON t.id_type_flux = f.id_type_flux
        JOIN dim_calendrier c ON c.date_id = f.date_id
        WHERE f.statut = 'REALISE'
          AND c.date > DATE_SUB('{DATE_FIN_HISTO}', INTERVAL {FENETRE_MOYENNE_JOURS} DAY)
          AND t.libelle IN ('INTERETS_VERSES', 'INTERETS_RECUS', 'RETRAITS_CLIENTS')
        GROUP BY f.id_filiale, t.libelle""", engine).set_index(["id_filiale", "libelle"]).moyenne
    return filiales, prev, position, marche, moyennes


def main():
    engine = get_engine()
    filiales, prev, position, marche, moyennes = charger(engine)

    lignes = []
    for fil in filiales.itertuples():
        p = prev[prev.id_filiale == fil.id_filiale]
        ouvre = p[f"ouvre_{fil.pays.lower()}"].astype(int).to_numpy()
        base = p.montant_prevu.astype(float).to_numpy()
        spot = float(marche.loc[fil.devise_principale, "taux_change_usd"])
        taux_actuel = float(marche.loc[fil.devise_principale, "taux_directeur"])
        moy = moyennes.loc[fil.id_filiale]
        pos0 = float(position[fil.id_filiale])

        for libelle, type_choc, valeur in SCENARIOS:
            facteur_change, delta = 1.0, 0.0
            if type_choc == "TAUX_CHANGE":
                facteur_change = 1 + valeur / 100
            elif type_choc == "TAUX_DIRECTEUR":
                hausse_relative = valeur / taux_actuel
                delta = (-moy["INTERETS_VERSES"] * hausse_relative
                         + moy["INTERETS_RECUS"] * hausse_relative * INDEXATION_INTERETS_RECUS)
            elif type_choc == "RETRAIT_DEPOTS":
                delta = -moy["RETRAITS_CLIENTS"] * valeur / 100
            stresse = base + float(delta) * ouvre

            lignes.append(pd.DataFrame({
                "libelle_scenario": libelle, "date_cible": p.date_cible.to_numpy(),
                "id_filiale": fil.id_filiale, "code_devise": fil.devise_principale,
                "type_choc": type_choc, "valeur_choc": valeur,
                "montant_base": base * spot,
                "montant_stresse": stresse * spot * facteur_change,
                "position_base_usd": (pos0 + base.cumsum()) * spot,
                "position_stressee_usd": (pos0 + stresse.cumsum()) * spot * facteur_change,
            }))

    montants = ["montant_base", "montant_stresse", "position_base_usd", "position_stressee_usd"]
    resultat = pd.concat(lignes).round({m: 2 for m in montants})
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM fait_scenario_stress")
        resultat.to_sql("fait_scenario_stress", conn, if_exists="append", index=False)

    j30 = resultat[resultat.date_cible == resultat.date_cible.max()].copy()
    j30["impact_usd"] = j30.position_stressee_usd - j30.position_base_usd
    j30["filiale"] = j30.id_filiale.map(filiales.set_index("id_filiale").nom_filiale)
    print("[stress] position à J+30 (USD) :")
    print(j30[["libelle_scenario", "filiale", "position_base_usd", "position_stressee_usd", "impact_usd"]]
          .to_string(index=False, float_format=lambda x: f"{x / 1e6:,.1f} M"))


if __name__ == "__main__":
    main()
