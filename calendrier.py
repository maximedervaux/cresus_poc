"""Événements calendaires bancaires connus à l'avance (paie, échéances, impôts...).

Utilisé par la simulation des sources ET comme variables explicatives des modèles :
un trésorier connaît les dates de paie ou d'échéances de crédits, le modèle aussi.
"""
import pandas as pd


def evenements_calendaires(jours_ouvres):
    """Retourne {événement: set(dates)} à partir de la liste des jours ouvrés d'une filiale."""
    s = pd.Series(pd.to_datetime(list(jours_ouvres))).sort_values()
    ev = {"echeance": set(), "salaire": set(), "impot": set(), "fin_mois": set()}
    for _, j in s.groupby(s.dt.to_period("M")):
        for jour_echeance in (5, 10):                      # échéances de crédits
            ev["echeance"].add(j[j.dt.day >= jour_echeance].min())
        ev["salaire"].add(j[j.dt.day <= 27].max())         # paie le 27 (ou veille ouvrée)
        ev["fin_mois"].update(j.nlargest(3))               # 3 derniers jours ouvrés
        if j.iloc[0].month in (3, 6, 9, 12):               # acomptes d'impôt trimestriels
            ev["impot"].add(j[j.dt.day >= 15].min())
    return {k: {d for d in v if pd.notna(d)} for k, v in ev.items()}
