"""Sources externes : taux de change (API BCE via Frankfurter) et taux directeurs
(API BCE Data Portal et Banque du Canada Valet).

Produit taux_change.csv (EUR/CAD, EUR/XAF), valeur_usd.csv (EUR/USD) et
taux_directeurs.csv. Récupération en différé (batch quotidien), pas en temps réel.
"""
from datetime import timedelta
from io import StringIO

import pandas as pd
import requests

from config import DATE_DEBUT, DATE_FIN_HISTO, PARITE_EUR_XAF, SOURCES_DIR

URL_API = "https://api.frankfurter.app/{debut}..{fin}?from=EUR&to=USD,CAD"
# Taux de la facilité de dépôt BCE (série quotidienne)
URL_BCE_DFR = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
               "?startPeriod={debut}&endPeriod={fin}&format=csvdata")
# Cible du taux du financement à un jour, Banque du Canada (série V39079, jours ouvrés)
URL_BDC_V39079 = "https://www.bankofcanada.ca/valet/observations/V39079/json?start_date={debut}&end_date={fin}"
# Profondeur d'historique avant DATE_DEBUT pour connaître le taux en vigueur au début de la fenêtre
RECUL_TAUX_DIRECTEURS = timedelta(days=365)

# La BEAC ne publie pas d'API : décisions du TIAO saisies manuellement (date d'effet, taux %).
DECISIONS_BEAC = [
    ("2023-03-27", 5.00),
    ("2025-03-24", 4.50),
]


def _decisions(serie, code_devise, banque_centrale):
    """Réduit une série quotidienne aux seules dates de changement de taux (dates d'effet)."""
    serie = serie.dropna().sort_index()
    serie = serie[serie.ne(serie.shift())]
    return pd.DataFrame({"date_effet": serie.index, "code_devise": code_devise,
                         "banque_centrale": banque_centrale, "taux_pct": serie.values})


def taux_directeurs():
    debut, fin = DATE_DEBUT - RECUL_TAUX_DIRECTEURS, DATE_FIN_HISTO

    reponse = requests.get(URL_BCE_DFR.format(debut=debut, fin=fin), timeout=30)
    reponse.raise_for_status()
    bce = pd.read_csv(StringIO(reponse.text), usecols=["TIME_PERIOD", "OBS_VALUE"])
    bce = bce.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float)

    reponse = requests.get(URL_BDC_V39079.format(debut=debut, fin=fin), timeout=30)
    reponse.raise_for_status()
    bdc = pd.Series({obs["d"]: float(obs["V39079"]["v"])
                     for obs in reponse.json()["observations"] if "V39079" in obs})

    beac = pd.DataFrame(DECISIONS_BEAC, columns=["date_effet", "taux_pct"]) \
        .assign(code_devise="XAF", banque_centrale="BEAC (TIAO)")
    return pd.concat([_decisions(bce, "EUR", "BCE (facilité de dépôt)"),
                      _decisions(bdc, "CAD", "Banque du Canada"),
                      beac[["date_effet", "code_devise", "banque_centrale", "taux_pct"]]],
                     ignore_index=True)


def main():
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    reponse = requests.get(URL_API.format(debut=DATE_DEBUT, fin=DATE_FIN_HISTO), timeout=30)
    reponse.raise_for_status()
    cours = reponse.json()["rates"]

    taux_change, valeur_usd = [], []
    for jour, valeurs in sorted(cours.items()):
        taux_change.append((jour, "EUR", "CAD", valeurs["CAD"]))
        # Le XAF n'est pas coté par la BCE : parité fixe garantie par le Trésor français
        taux_change.append((jour, "EUR", "XAF", PARITE_EUR_XAF))
        valeur_usd.append((jour, valeurs["USD"]))

    pd.DataFrame(taux_change, columns=["date", "devise_base", "devise_cotee", "taux"]) \
        .to_csv(SOURCES_DIR / "taux_change.csv", index=False)
    pd.DataFrame(valeur_usd, columns=["date", "eur_usd"]) \
        .to_csv(SOURCES_DIR / "valeur_usd.csv", index=False)
    directeurs = taux_directeurs()
    directeurs.to_csv(SOURCES_DIR / "taux_directeurs.csv", index=False)
    print(f"[marché] {len(valeur_usd)} jours de cotation BCE récupérés "
          f"({valeur_usd[0][0]} -> {valeur_usd[-1][0]})")
    print(f"[marché] {len(directeurs)} décisions de taux directeurs "
          f"({', '.join(f'{d}: {n}' for d, n in directeurs.code_devise.value_counts(sort=False).items())})")


if __name__ == "__main__":
    main()
