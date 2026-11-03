"""Restitution : création des vues Power BI et export CSV du modèle.

Les exports permettent d'alimenter Power BI par simple import de fichiers
lorsque la connexion directe MySQL n'est pas disponible (ex. Power BI Service sans passerelle).
"""
import pandas as pd

from config import EXPORT_DIR, SQL_DIR
from db import executer_script_sql, get_engine

OBJETS_EXPORTES = [
    "dim_filiale", "dim_devise", "dim_calendrier", "dim_type_flux",
    "fait_flux_tresorerie", "fait_taux", "fait_prevision", "fait_prevision_taux",
    "fait_scenario_stress", "perf_modele", "etl_controle_qualite",
    "v_position_realisee", "v_position_projetee", "v_backtest", "v_projection_taux", "v_stress_synthese",
]


def main():
    executer_script_sql(SQL_DIR / "vues.sql")
    engine = get_engine()
    EXPORT_DIR.mkdir(exist_ok=True)
    for objet in OBJETS_EXPORTES:
        pd.read_sql(f"SELECT * FROM {objet}", engine).to_csv(EXPORT_DIR / f"{objet}.csv", index=False)
    print(f"[restitution] vues créées, {len(OBJETS_EXPORTES)} fichiers exportés dans {EXPORT_DIR}")


if __name__ == "__main__":
    main()
