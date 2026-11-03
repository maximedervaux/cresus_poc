"""ETL Crésus (MOE §2.2.2) : sources hétérogènes -> staging -> modèle en étoile.

Étapes : chargement brut (stg_*), dédoublonnage, filtrage des lignes non pertinentes,
standardisation (dates, montants, séparateurs, libellés), contrôle de cohérence,
conversion en USD, chargement des dimensions et des faits, journal qualité.
"""
from dataclasses import asdict, dataclass

import pandas as pd

from config import (DATE_DEBUT, DATE_FIN_CALENDRIER, DATE_FIN_HISTO, DEVISES, FILIALES,
                    SOURCES_DIR, SQL_DIR)
from db import executer_script_sql, get_engine
from referentiels import CODE_CI, LIB_CA, LIB_FR, TYPES_FLUX

SOURCES = {  # table staging -> (fichier, options de lecture)
    "stg_flux_fr": ("flux_tresorerie_FR.csv", {"sep": ";", "encoding": "cp1252"}),
    "stg_flux_ca": ("flux_tresorerie_CA.csv", {"sep": ","}),
    "stg_flux_ci": ("flux_tresorerie_CI.csv", {"sep": "|"}),
    "stg_taux_change": ("taux_change.csv", {}),
    "stg_valeur_usd": ("valeur_usd.csv", {}),
    "stg_taux_directeurs": ("taux_directeurs.csv", {}),
    "stg_jours_feries": ("calendrier_jours_feries.csv", {}),
}
COLONNES_STD = ["date", "type_flux", "montant", "statut", "code_devise"]


@dataclass
class Controle:
    source: str
    lignes_lues: int
    doublons: int = 0
    non_pertinentes: int = 0
    rejets: int = 0
    lignes_chargees: int = 0


# ------------------------------- EXTRACT ---------------------------------
def extraire():
    return {table: pd.read_csv(SOURCES_DIR / fichier, dtype=str, keep_default_na=False, **opts)
            for table, (fichier, opts) in SOURCES.items()}


def charger_staging(engine, brut):
    horodatage = pd.Timestamp.now().floor("s")
    for table, df in brut.items():
        df.assign(date_chargement=horodatage).to_sql(table, engine, if_exists="replace", index=False)


# ------------------------------ TRANSFORM --------------------------------
def _nettoyer(df, ctrl, est_pertinent):
    """Supprime espaces parasites, doublons exacts et lignes non pertinentes."""
    df = df.apply(lambda c: c.str.strip())
    n = len(df)
    df = df.drop_duplicates()
    ctrl.doublons = n - len(df)
    garder = est_pertinent(df)
    ctrl.non_pertinentes = int((~garder).sum())
    return df[garder]


def _valider(std, ctrl):
    """Rejette les lignes incomplètes ou non reconnues par le référentiel."""
    ok = std[COLONNES_STD].notna().all(axis=1)
    ctrl.rejets = int((~ok).sum())
    std = std[ok].copy()
    std["montant"] = std.montant.abs().round(2)  # le sens est porté par DIM_TYPE_FLUX
    ctrl.lignes_chargees = len(std)
    return std


def transformer_fr(brut):
    ctrl = Controle("flux_tresorerie_FR.csv", len(brut))
    df = _nettoyer(brut, ctrl, lambda d: d.Statut != "Annulé")
    std = pd.DataFrame({
        "date": pd.to_datetime(df.Date_Operation, format="%d/%m/%Y", errors="coerce"),
        "type_flux": df.Libelle.map({v: k for k, v in LIB_FR.items()}),
        "montant": pd.to_numeric(df.Montant.str.replace(",", ".", regex=False), errors="coerce"),
        "statut": df.Statut.map({"Réalisé": "REALISE", "Prévisionnel": "PREVISIONNEL"}),
        "code_devise": df.Devise.str.upper(),
    })
    return _valider(std, ctrl), ctrl


def transformer_ca(brut):
    ctrl = Controle("flux_tresorerie_CA.csv", len(brut))
    brut = brut.assign(category=brut.category.str.strip().str.lower())
    df = _nettoyer(brut, ctrl, lambda d: d.category != "internal transfer")
    std = pd.DataFrame({
        "date": pd.to_datetime(df.txn_date, format="%m/%d/%Y", errors="coerce"),
        "type_flux": df.category.map({v.lower(): k for k, v in LIB_CA.items()}),
        "montant": pd.to_numeric(df.amount, errors="coerce"),  # signé à la source
        "statut": df.status.str.lower().map({"actual": "REALISE", "forecast": "PREVISIONNEL"}),
        "code_devise": df.currency.str.upper(),
    })
    return _valider(std, ctrl), ctrl


def transformer_ci(brut):
    ctrl = Controle("flux_tresorerie_CI.csv", len(brut))
    df = _nettoyer(brut, ctrl, lambda d: d.NATURE_FLUX != "TEST")
    type_flux = df.NATURE_FLUX.map({v: k for k, v in CODE_CI.items()})
    # Contrôle de cohérence : le sens déclaré doit correspondre au référentiel
    sens_ok = df.SENS.map({"C": "ENCAISSEMENT", "D": "DECAISSEMENT"}) == type_flux.map(TYPES_FLUX)
    std = pd.DataFrame({
        "date": pd.to_datetime(df.DATE_VALEUR, format="%Y%m%d", errors="coerce"),
        "type_flux": type_flux.where(sens_ok),
        "montant": pd.to_numeric(df.MONTANT_XAF.str.replace(r"\s", "", regex=True), errors="coerce"),
        "statut": df.ETAT.map({"R": "REALISE", "P": "PREVISIONNEL"}),
        "code_devise": "XAF",
    })
    return _valider(std, ctrl), ctrl


def construire_calendrier(feries):
    feries = feries.assign(date=pd.to_datetime(feries.date))
    jours = pd.DataFrame({"date": pd.date_range(DATE_DEBUT, DATE_FIN_CALENDRIER, freq="D")})
    jours["date"] = jours.date.astype("datetime64[ns]")
    cal = jours.assign(date_id=jours.date.dt.strftime("%Y%m%d").astype(int),
                       jour=jours.date.dt.day, mois=jours.date.dt.month, annee=jours.date.dt.year,
                       jour_semaine=jours.date.dt.day_of_week + 1)
    for pays in ("FRA", "CAN", "CIV"):
        ferie = cal.date.isin(feries.loc[feries.pays == pays, "date"])
        cal[f"ouvre_{pays.lower()}"] = (cal.jour_semaine <= 5) & ~ferie
    return cal


def construire_taux(brut, cal):
    """Taux quotidiens : valeur en USD d'une unité de devise + taux directeur en vigueur."""
    usd = brut["stg_valeur_usd"].assign(date=lambda d: pd.to_datetime(d.date),
                                        eur_usd=lambda d: d.eur_usd.astype(float))
    tc = brut["stg_taux_change"].assign(date=lambda d: pd.to_datetime(d.date),
                                        taux=lambda d: d.taux.astype(float))
    eur_x = tc.pivot(index="date", columns="devise_cotee", values="taux")
    cours = usd.set_index("date").join(eur_x)
    valeur_usd = pd.DataFrame({
        "EUR": cours.eur_usd,
        "CAD": cours.eur_usd / cours.CAD,
        "XAF": cours.eur_usd / cours.XAF,
        "USD": 1.0,
    })
    # Pas de cotation les week-ends / jours fériés BCE : on reporte le dernier cours connu
    jours = cal.loc[cal.date <= pd.Timestamp(DATE_FIN_HISTO), "date"]
    valeur_usd = valeur_usd.reindex(jours).ffill().bfill()
    taux = (valeur_usd.rename_axis("date").reset_index()
            .melt(id_vars="date", var_name="code_devise", value_name="taux_change_usd"))

    td = brut["stg_taux_directeurs"].assign(date=lambda d: pd.to_datetime(d.date_effet),
                                            taux_directeur=lambda d: d.taux_pct.astype(float))
    taux["date"] = taux.date.astype("datetime64[ns]")
    td["date"] = td.date.astype("datetime64[ns]")
    taux = pd.merge_asof(taux.sort_values("date"), td[["date", "code_devise", "taux_directeur"]].sort_values("date"),
                         on="date", by="code_devise", direction="backward")
    return taux.merge(cal[["date", "date_id"]].astype({"date": "datetime64[ns]"}), on="date")


def convertir_usd(flux, taux):
    """montant_usd = montant x cours du jour (dernier cours connu pour les dates futures)."""
    flux = flux.assign(date=flux.date.astype("datetime64[ns]"))
    flux = pd.merge_asof(flux.sort_values("date"), taux[["date", "code_devise", "taux_change_usd"]].sort_values("date"),
                         on="date", by="code_devise", direction="backward")
    return flux.assign(montant_usd=(flux.montant * flux.taux_change_usd).round(2))


# -------------------------------- LOAD -----------------------------------
def main():
    executer_script_sql(SQL_DIR / "schema.sql", sur_serveur=True)
    engine = get_engine()

    brut = extraire()
    charger_staging(engine, brut)

    cal = construire_calendrier(brut["stg_jours_feries"])
    taux = construire_taux(brut, cal)

    resultats = [transformer_fr(brut["stg_flux_fr"]), transformer_ca(brut["stg_flux_ca"]),
                 transformer_ci(brut["stg_flux_ci"])]
    flux = pd.concat([std.assign(id_filiale=f["id_filiale"]) for (std, _), f in zip(resultats, FILIALES)])
    flux = convertir_usd(flux, taux)

    types = pd.DataFrame({"id_type_flux": range(1, len(TYPES_FLUX) + 1),
                          "libelle": list(TYPES_FLUX), "sens": list(TYPES_FLUX.values())})
    flux = flux.merge(cal[["date", "date_id"]], on="date") \
               .merge(types[["id_type_flux", "libelle"]], left_on="type_flux", right_on="libelle")

    with engine.begin() as conn:
        pd.DataFrame(DEVISES.items(), columns=["code_devise", "libelle_devise"]) \
            .to_sql("dim_devise", conn, if_exists="append", index=False)
        pd.DataFrame(FILIALES).drop(columns="iso2").to_sql("dim_filiale", conn, if_exists="append", index=False)
        cal.to_sql("dim_calendrier", conn, if_exists="append", index=False)
        types.to_sql("dim_type_flux", conn, if_exists="append", index=False)
        taux[["date_id", "code_devise", "taux_change_usd", "taux_directeur"]] \
            .to_sql("fait_taux", conn, if_exists="append", index=False)
        flux[["date_id", "id_filiale", "code_devise", "id_type_flux", "montant", "montant_usd", "statut"]] \
            .to_sql("fait_flux_tresorerie", conn, if_exists="append", index=False, chunksize=5000)
        pd.DataFrame([asdict(c) for _, c in resultats]) \
            .assign(date_execution=pd.Timestamp.now().floor("s")) \
            .to_sql("etl_controle_qualite", conn, if_exists="append", index=False)

    print("[etl] contrôle qualité :")
    print(pd.DataFrame([asdict(c) for _, c in resultats]).to_string(index=False))
    print(f"[etl] {len(flux)} flux chargés, {len(taux)} taux, {len(cal)} jours de calendrier")


if __name__ == "__main__":
    main()
