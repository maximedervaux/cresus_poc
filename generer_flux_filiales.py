"""Sources internes simulées : extractions des systèmes de trésorerie des 3 filiales.

Chaque filiale a volontairement son propre format :
  - FR : séparateur « ; », décimale « , », date JJ/MM/AAAA, encodage Windows-1252, libellés FR
  - CA : séparateur « , », date MM/JJ/AAAA, libellés EN, décaissements en montants négatifs
  - CI : séparateur « | », date AAAAMMJJ, codes courts, sens C/D, milliers séparés par espace
et contient des défauts de qualité (doublons, montants vides, lignes non pertinentes)
que l'ETL doit traiter.

Les lignes prévisionnelles simulent la prévision manuelle actuelle des trésoriers
(méthode tableur) : elles servent de référence pour mesurer le gain des modèles.
"""
import holidays
import numpy as np
import pandas as pd

from calendrier import evenements_calendaires
from config import DATE_DEBUT, DATE_FIN_CALENDRIER, DATE_FIN_HISTO, FILIALES, HORIZON_JOURS, SOURCES_DIR
from referentiels import CODE_CI, LIB_CA, LIB_FR, TYPES_FLUX

rng = np.random.default_rng(2017)  # graine fixe : jeu de données reproductible

# Volume journalier de référence (devise locale), solde d'ouverture, poids des dépôts
PROFILS = {
    "FR": {"echelle": 50e6, "ouverture": 400e6, "poids_depots": 0.955},
    "CA": {"echelle": 30e6, "ouverture": 250e6, "poids_depots": 0.955},
    "CI": {"echelle": 8e9, "ouverture": 150e9, "poids_depots": 0.94},
}
FIN_HISTO = pd.Timestamp(DATE_FIN_HISTO)
# Prévisions manuelles : une pour le backtest (octobre), une pour l'horizon de production
DATES_PREVISION_MANUELLE = [FIN_HISTO - pd.Timedelta(days=HORIZON_JOURS), FIN_HISTO]

# Jours fériés par filiale (pour générer les flux récurrents sur les jours ouvrés)
def jours_ouvres(iso2):
    feries = holidays.country_holidays(iso2, years=range(DATE_DEBUT.year, DATE_FIN_CALENDRIER.year + 1))
    jours = pd.date_range(DATE_DEBUT, DATE_FIN_CALENDRIER, freq="D")
    return [d for d in jours if d.weekday() < 5 and d.date() not in feries]

def generer_realise(profil, ouvres, ev):
    """Flux réalisés simulés : montants journaliers avec bruit log-normal, croissance de 10 % sur la période."""
    e = profil["echelle"]
    ouvres = [d for d in ouvres if d <= FIN_HISTO]
    lignes = [(pd.Timestamp(DATE_DEBUT), "REPORT_A_NOUVEAU", profil["ouverture"])]
    for i, d in enumerate(ouvres):
        croissance = 1 + 0.10 * i / len(ouvres)  # +10 % d'activité sur la période

        def ajouter(type_flux, montant):
            lignes.append((d, type_flux, montant * rng.lognormal(0, 0.12)))

        ajouter("DEPOTS_CLIENTS", e * profil["poids_depots"] * croissance * (1.6 if d.day <= 3 else 1))
        ajouter("REMBOURSEMENTS_CREDITS", e * 0.55 * croissance * (2 if d in ev["echeance"] else 1))
        ajouter("COMMISSIONS", e * 0.05 * croissance)
        ajouter("INTERETS_RECUS", e * 0.08)
        ajouter("RETRAITS_CLIENTS", e * 0.95 * croissance
                * (1.2 if d.weekday() == 4 or d in ev["fin_mois"] else 1)
                * (1.15 if d.month == 12 else 1))
        ajouter("OCTROI_CREDITS", e * 0.55 * croissance)
        ajouter("FRAIS_GENERAUX", e * 0.06)
        ajouter("INTERETS_VERSES", e * 0.05)
        if d in ev["salaire"]:
            ajouter("SALAIRES", e * 0.9)
        if d in ev["impot"]:
            ajouter("IMPOTS", e * 1.5)
    return pd.DataFrame(lignes, columns=["date", "type_flux", "montant"]).assign(statut="REALISE")

def generer_prevision_manuelle(realise, date_generation, ouvres, ev):
    """Méthode tableur : moyenne par jour ouvré sur 3 mois pour les flux récurrents,
    dernier montant connu pour la paie et les impôts placés à leur date."""
    fenetre = realise[(realise.date > date_generation - pd.Timedelta(days=90))
                      & (realise.date <= date_generation)
                      & (realise.type_flux != "REPORT_A_NOUVEAU")]
    nb_jours = fenetre.date.nunique()
    cibles = [d for d in ouvres if date_generation < d <= date_generation + pd.Timedelta(days=HORIZON_JOURS)]
    ponctuels = {"SALAIRES": "salaire", "IMPOTS": "impot"}
    lignes = []
    for type_flux, g in fenetre.groupby("type_flux"):
        if type_flux in ponctuels:
            dernier = g.sort_values("date").montant.iloc[-1]
            lignes += [(d, type_flux, dernier) for d in cibles if d in ev[ponctuels[type_flux]]]
        else:
            moyenne = g.montant.sum() / nb_jours
            lignes += [(d, type_flux, moyenne) for d in cibles]
    return pd.DataFrame(lignes, columns=["date", "type_flux", "montant"]).assign(statut="PREVISIONNEL")

def degrader(df, col_montant, rendre_non_pertinent):
    """Injecte doublons, montants manquants et lignes non pertinentes."""
    df = df.copy()
    df.loc[df.sample(frac=0.002, random_state=3).index, col_montant] = ""
    doublons = df.sample(frac=0.005, random_state=1)
    parasites = rendre_non_pertinent(df.sample(frac=0.003, random_state=2).copy())
    return pd.concat([df, doublons, parasites]).sort_index(kind="stable")

def ecrire_fr(df, chemin):
    """Écrit le flux de la filiale française dans le format attendu par l'ETL."""
    out = pd.DataFrame({
        "Date_Operation": df.date.dt.strftime("%d/%m/%Y"),
        "Libelle": df.type_flux.map(LIB_FR),
        "Montant": df.montant.map(lambda x: f"{x:.2f}".replace(".", ",")),
        "Devise": "EUR",
        "Statut": df.statut.map({"REALISE": "Réalisé", "PREVISIONNEL": "Prévisionnel"}),
    })
    out = degrader(out, "Montant", lambda p: p.assign(Statut="Annulé"))
    out.to_csv(chemin, sep=";", index=False, encoding="cp1252")

def ecrire_ca(df, chemin):
    """Écrit le flux de la filiale canadienne dans le format attendu par l'ETL."""
    signe = np.where(df.type_flux.map(TYPES_FLUX) == "DECAISSEMENT", -1, 1)
    out = pd.DataFrame({
        "txn_date": df.date.dt.strftime("%m/%d/%Y"),
        "category": df.type_flux.map(LIB_CA),
        "amount": (df.montant * signe).map(lambda x: f"{x:.2f}"),
        "currency": "CAD",
        "status": df.statut.map({"REALISE": "Actual", "PREVISIONNEL": "Forecast"}),
    })
    casse = out.sample(frac=0.05, random_state=4).index           # saisie incohérente
    out.loc[casse, "category"] = out.loc[casse, "category"].str.lower() + " "
    out = degrader(out, "amount", lambda p: p.assign(category="Internal transfer"))
    out.to_csv(chemin, sep=",", index=False)

def ecrire_ci(df, chemin):
    """Écrit le flux de la filiale ivoirienne dans le format attendu par l'ETL."""
    out = pd.DataFrame({
        "DATE_VALEUR": df.date.dt.strftime("%Y%m%d"),
        "NATURE_FLUX": df.type_flux.map(CODE_CI),
        "SENS": df.type_flux.map(TYPES_FLUX).map({"ENCAISSEMENT": "C", "DECAISSEMENT": "D"}),
        "MONTANT_XAF": df.montant.map(lambda x: f"{round(x):,}".replace(",", " ")),
        "ETAT": df.statut.map({"REALISE": "R", "PREVISIONNEL": "P"}),
    })
    out = degrader(out, "MONTANT_XAF", lambda p: p.assign(NATURE_FLUX="TEST"))
    out.to_csv(chemin, sep="|", index=False)


ECRIVAINS = {"FR": ecrire_fr, "CA": ecrire_ca, "CI": ecrire_ci}

def main():
    """Génère les fichiers sources simulés pour les 3 filiales."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    feries = []
    for filiale in FILIALES:
        iso2 = filiale["iso2"]
        ouvres = jours_ouvres(iso2)
        ev = evenements_calendaires(ouvres)
        realise = generer_realise(PROFILS[iso2], ouvres, ev)
        manuel = pd.concat([generer_prevision_manuelle(realise, d, ouvres, ev) for d in DATES_PREVISION_MANUELLE])
        flux = pd.concat([realise, manuel]).sort_values(["date", "statut"], kind="stable").reset_index(drop=True)
        chemin = SOURCES_DIR / f"flux_tresorerie_{iso2}.csv"
        ECRIVAINS[iso2](flux, chemin)
        print(f"[sources] {chemin.name} : {len(flux)} mouvements générés")

        for jour, libelle in holidays.country_holidays(
                iso2, years=range(DATE_DEBUT.year, DATE_FIN_CALENDRIER.year + 1)).items():
            feries.append((jour.isoformat(), filiale["pays"], libelle))

    pd.DataFrame(sorted(feries), columns=["date", "pays", "libelle"]) \
        .to_csv(SOURCES_DIR / "calendrier_jours_feries.csv", index=False)


if __name__ == "__main__":
    main()
