"""Moteur prédictif (MOE §2.1.2 / §2.2.4) : Prophet et ARIMA à 30 jours.

1. BACKTEST   : modèles entraînés jusqu'à J-30, comparés au réalisé des 30 derniers jours
               et à la prévision manuelle actuelle des trésoriers (référence « MANUEL »).
2. PRODUCTION : modèles ré-entraînés sur tout l'historique, prévision J+1 -> J+30.
3. TAUX       : projection à 30 jours du cours de chaque devise contre USD.

Cible prédite : flux net journalier (encaissements - décaissements) par filiale.
Variables explicatives : calendrier bancaire connu à l'avance (jours ouvrés, paie,
échéances de crédits, impôts, fin de mois...).
"""
import logging
import warnings

import numpy as np
import pandas as pd
from prophet import Prophet
from statsmodels.tsa.statespace.sarimax import SARIMAX

from calendrier import evenements_calendaires
from config import DATE_FIN_HISTO, HORIZON_JOURS
from db import get_engine

logging.getLogger("cmdstanpy").disabled = True  # logs Stan très verbeux
logging.getLogger("prophet").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", module="statsmodels")

FIN_HISTO = pd.Timestamp(DATE_FIN_HISTO)
RUNS = {"BACKTEST": FIN_HISTO - pd.Timedelta(days=HORIZON_JOURS), "PRODUCTION": FIN_HISTO}
FEATURES = ["ouvre", "debut_mois", "echeance", "salaire", "impot", "fin_mois", "vendredi", "decembre"]
NIVEAU_CONFIANCE = 0.80


def features_calendaires(cal, pays):
    ouvre = cal[f"ouvre_{pays.lower()}"].astype(bool)
    ev = evenements_calendaires(cal.date[ouvre])
    X = pd.DataFrame({"ds": cal.date})
    X["ouvre"] = ouvre.astype(int)
    X["debut_mois"] = (ouvre & (cal.date.dt.day <= 3)).astype(int)
    for evenement in ("echeance", "salaire", "impot", "fin_mois"):
        X[evenement] = cal.date.isin(ev[evenement]).astype(int)
    X["vendredi"] = (ouvre & (cal.date.dt.day_of_week == 4)).astype(int)
    X["decembre"] = (ouvre & (cal.date.dt.month == 12)).astype(int)
    return X


def prevoir_prophet(train, futur, regresseurs):
    echelle = train.y.abs().mean()
    m = Prophet(interval_width=NIVEAU_CONFIANCE, yearly_seasonality=False,
                weekly_seasonality=not regresseurs, daily_seasonality=False)
    for r in regresseurs:
        m.add_regressor(r)
    m.fit(train.assign(y=train.y / echelle)[["ds", "y"] + regresseurs])
    p = m.predict(futur[["ds"] + regresseurs])
    return pd.DataFrame({"ds": futur.ds.values, "prevu": p.yhat.values * echelle,
                         "bas": p.yhat_lower.values * echelle, "haut": p.yhat_upper.values * echelle})


def prevoir_arima(train, futur, regresseurs, ordre=(1, 0, 1)):
    echelle = train.y.abs().mean()
    exog = train[regresseurs].to_numpy() if regresseurs else None
    modele = SARIMAX(train.y.to_numpy() / echelle, exog=exog, order=ordre,
                     trend="c" if ordre[1] == 0 else "n").fit(disp=False)
    fc = modele.get_forecast(len(futur), exog=futur[regresseurs].to_numpy() if regresseurs else None)
    ic = fc.conf_int(alpha=1 - NIVEAU_CONFIANCE)
    return pd.DataFrame({"ds": futur.ds.values, "prevu": fc.predicted_mean * echelle,
                         "bas": ic[:, 0] * echelle, "haut": ic[:, 1] * echelle})


def evaluer(reel, prevu):
    erreur = prevu - reel
    return {"nb_jours": len(reel), "mae": np.abs(erreur).mean(),
            "wape_pct": 100 * np.abs(erreur).sum() / np.abs(reel).sum(),
            "ecart_position_j30": erreur.sum()}


def charger(engine):
    cal = pd.read_sql("SELECT * FROM dim_calendrier ORDER BY date", engine, parse_dates=["date"])
    filiales = pd.read_sql("SELECT * FROM dim_filiale", engine)
    flux = pd.read_sql("""
        SELECT f.id_filiale, c.date, f.statut,
               SUM(CASE WHEN t.sens = 'ENCAISSEMENT' THEN f.montant ELSE -f.montant END) AS flux_net
        FROM fait_flux_tresorerie f
        JOIN dim_calendrier c ON c.date_id = f.date_id
        JOIN dim_type_flux t ON t.id_type_flux = f.id_type_flux
        WHERE t.libelle <> 'REPORT_A_NOUVEAU'
        GROUP BY f.id_filiale, c.date, f.statut""", engine, parse_dates=["date"])
    taux = pd.read_sql("""
        SELECT c.date, t.code_devise, t.taux_change_usd FROM fait_taux t
        JOIN dim_calendrier c ON c.date_id = t.date_id WHERE t.code_devise <> 'USD'
        ORDER BY c.date""", engine, parse_dates=["date"])
    return cal, filiales, flux, taux


def prevoir_flux(cal, filiales, flux):
    modeles = {"PROPHET": prevoir_prophet, "ARIMA": prevoir_arima}
    previsions, perfs = [], []
    for fil in filiales.itertuples():
        X = features_calendaires(cal, fil.pays)
        realise = flux[(flux.id_filiale == fil.id_filiale) & (flux.statut == "REALISE")].set_index("date").flux_net
        serie = X[X.ds <= FIN_HISTO].assign(y=lambda d: d.ds.map(realise).fillna(0.0))

        for type_run, date_gen in RUNS.items():
            train = serie[serie.ds <= date_gen]
            futur = X[(X.ds > date_gen) & (X.ds <= date_gen + pd.Timedelta(days=HORIZON_JOURS))]
            for nom, fonction in modeles.items():
                p = fonction(train, futur, FEATURES)
                p.loc[futur.ouvre.values == 0, ["prevu", "bas", "haut"]] = 0.0  # aucun flux jour fermé
                previsions.append(p.assign(type_run=type_run, date_generation=date_gen, modele=nom,
                                           id_filiale=fil.id_filiale, code_devise=fil.devise_principale))
                if type_run == "BACKTEST":
                    reel = serie.set_index("ds").y.reindex(p.ds).to_numpy()
                    perfs.append({"id_filiale": fil.id_filiale, "modele": nom, "date_generation": date_gen,
                                  **evaluer(reel, p.prevu.to_numpy())})

        # Référence : prévision manuelle actuelle des trésoriers sur la même fenêtre
        fenetre = X[(X.ds > RUNS["BACKTEST"]) & (X.ds <= FIN_HISTO)].ds
        manuel = flux[(flux.id_filiale == fil.id_filiale) & (flux.statut == "PREVISIONNEL")] \
            .set_index("date").flux_net.reindex(fenetre).fillna(0.0).to_numpy()
        reel = serie.set_index("ds").y.reindex(fenetre).to_numpy()
        perfs.append({"id_filiale": fil.id_filiale, "modele": "MANUEL", "date_generation": RUNS["BACKTEST"],
                      **evaluer(reel, manuel)})

    perfs = pd.DataFrame(perfs)
    candidats = perfs[perfs.modele != "MANUEL"]
    meilleurs = candidats.loc[candidats.groupby("id_filiale").wape_pct.idxmin()].index
    perfs["retenu"] = perfs.index.isin(meilleurs)
    previsions = pd.concat(previsions).rename(columns={"ds": "date_cible", "prevu": "montant_prevu",
                                                       "bas": "borne_basse", "haut": "borne_haute"})
    return previsions, perfs


def prevoir_taux(taux):
    futur = pd.DataFrame({"ds": pd.date_range(FIN_HISTO + pd.Timedelta(days=1), periods=HORIZON_JOURS)})
    sorties = []
    for devise, g in taux.groupby("code_devise"):
        train = g.rename(columns={"date": "ds", "taux_change_usd": "y"})[["ds", "y"]]
        for nom, p in {"PROPHET": prevoir_prophet(train, futur, []),
                       "ARIMA": prevoir_arima(train, futur, [], ordre=(1, 1, 1))}.items():
            sorties.append(p.assign(modele=nom, code_devise=devise, date_generation=FIN_HISTO))
    return pd.concat(sorties).rename(columns={"ds": "date_cible", "prevu": "taux_prevu",
                                              "bas": "borne_basse", "haut": "borne_haute"})


def main():
    engine = get_engine()
    cal, filiales, flux, taux = charger(engine)
    previsions, perfs = prevoir_flux(cal, filiales, flux)
    prev_taux = prevoir_taux(taux)

    with engine.begin() as conn:
        for table in ("fait_scenario_stress", "fait_prevision", "fait_prevision_taux", "perf_modele"):
            conn.exec_driver_sql(f"DELETE FROM {table}")
        previsions.round({"montant_prevu": 2, "borne_basse": 2, "borne_haute": 2}) \
            .to_sql("fait_prevision", conn, if_exists="append", index=False)
        prev_taux.to_sql("fait_prevision_taux", conn, if_exists="append", index=False)
        perfs.round({"mae": 2, "wape_pct": 2, "ecart_position_j30": 2}).to_sql("perf_modele", conn, if_exists="append", index=False)

    noms = filiales.set_index("id_filiale").nom_filiale
    print("[prédiction] backtest sur les 30 derniers jours (WAPE = erreur absolue pondérée) :")
    print(perfs.assign(filiale=perfs.id_filiale.map(noms))
          [["filiale", "modele", "wape_pct", "mae", "ecart_position_j30", "retenu"]]
          .round(1).to_string(index=False))
    print(f"[prédiction] {len(previsions)} prévisions de flux, {len(prev_taux)} prévisions de taux")


if __name__ == "__main__":
    main()
