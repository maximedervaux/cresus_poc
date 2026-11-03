"""Sources externes : taux de change (API BCE via Frankfurter) et taux directeurs.

Produit taux_change.csv (EUR/CAD, EUR/XAF), valeur_usd.csv (EUR/USD) et
taux_directeurs.csv, conformément au §2.3 du MOE. Récupération en différé
(batch quotidien), pas en temps réel (MOE §2.1.5).
"""
import pandas as pd
import requests

from config import DATE_DEBUT, DATE_FIN_HISTO, PARITE_EUR_XAF, SOURCES_DIR

URL_API = "https://api.frankfurter.app/{debut}..{fin}?from=EUR&to=USD,CAD"

# Décisions de politique monétaire (date d'effet, devise, banque centrale, taux %).
# Saisie manuelle indicative pour le POC ; en cible, alimentation via les API des banques centrales.
DECISIONS_TAUX_DIRECTEURS = [
    ("2024-10-23", "EUR", "BCE (facilité de dépôt)", 3.25),
    ("2024-12-18", "EUR", "BCE (facilité de dépôt)", 3.00),
    ("2025-02-05", "EUR", "BCE (facilité de dépôt)", 2.75),
    ("2025-03-12", "EUR", "BCE (facilité de dépôt)", 2.50),
    ("2025-04-23", "EUR", "BCE (facilité de dépôt)", 2.25),
    ("2025-06-11", "EUR", "BCE (facilité de dépôt)", 2.00),
    ("2024-10-23", "CAD", "Banque du Canada", 3.75),
    ("2024-12-11", "CAD", "Banque du Canada", 3.25),
    ("2025-01-29", "CAD", "Banque du Canada", 3.00),
    ("2025-03-12", "CAD", "Banque du Canada", 2.75),
    ("2025-09-17", "CAD", "Banque du Canada", 2.50),
    ("2025-10-29", "CAD", "Banque du Canada", 2.25),
    ("2023-03-27", "XAF", "BEAC (TIAO)", 5.00),
    ("2025-03-24", "XAF", "BEAC (TIAO)", 4.50),
]


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
    pd.DataFrame(DECISIONS_TAUX_DIRECTEURS,
                 columns=["date_effet", "code_devise", "banque_centrale", "taux_pct"]) \
        .to_csv(SOURCES_DIR / "taux_directeurs.csv", index=False)
    print(f"[marché] {len(valeur_usd)} jours de cotation BCE récupérés "
          f"({valeur_usd[0][0]} -> {valeur_usd[-1][0]})")


if __name__ == "__main__":
    main()
