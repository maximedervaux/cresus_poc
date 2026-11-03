"""Paramètres centraux de la pipeline Cresus POC."""
import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SOURCES_DIR = BASE_DIR / "data" / "sources"
SQL_DIR = BASE_DIR / "sql"

# Connexion MySQL (surchargeable : export CRESUS_DB_SERVER="mysql+pymysql://user:mdp@hote:3306")
DB_NAME = "cresus_poc"
DB_SERVER_URL = os.getenv("CRESUS_DB_SERVER", "mysql+pymysql://root@127.0.0.1:3306")
DB_URL = f"{DB_SERVER_URL}/{DB_NAME}?charset=utf8mb4"

# Fenêtre temporelle
DATE_DEBUT = date(2024, 11, 1)        # début de l'historique
DATE_FIN_HISTO = date(2026, 10, 31)   # dernier jour réalisé
HORIZON_JOURS = 30                    # horizon de prévision (30 jours par défaut)
DATE_FIN_CALENDRIER = date(2026, 12, 31)

DEVISE_REPORTING = "USD"              # devise de consolidation
PARITE_EUR_XAF = 655.957              # parité fixe franc CFA / euro

DEVISES = {
    "EUR": "EURO",
    "CAD": "DOLLAR CANADIEN",
    "XAF": "FRANC CFA BEAC",
    "USD": "DOLLAR AMERICAIN",
}

# seuil_alerte : position minimale (devise locale) sous laquelle la devise est à faible stock
FILIALES = [
    {"id_filiale": 1, "nom_filiale": "ZF_BANQUE_FRANCE", "pays": "FRA", "iso2": "FR",
     "zone_geo": "EUROPE", "devise_principale": "EUR", "seuil_alerte": 200e6},
    {"id_filiale": 2, "nom_filiale": "ZF_BANQUE_CANADA", "pays": "CAN", "iso2": "CA",
     "zone_geo": "AMERIQUE_NORD", "devise_principale": "CAD", "seuil_alerte": 100e6},
    {"id_filiale": 3, "nom_filiale": "ZF_BANQUE_COTE_IVOIRE", "pays": "CIV", "iso2": "CI",
     "zone_geo": "AFRIQUE_OUEST", "devise_principale": "XAF", "seuil_alerte": 90e9},
]
