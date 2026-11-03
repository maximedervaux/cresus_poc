"""Orchestration du POC (MOE §2.1.5) : à planifier quotidiennement (cron / Planificateur).

    python run_pipeline.py                 # chaîne complète
    python run_pipeline.py --sans-sources  # réutilise les fichiers sources existants
"""
import sys
import time

import etl
import extract_marche
import generer_flux_filiales
import prediction
import restitution
import stress


def main():
    etapes = [("ETL", etl.main), ("Prédiction", prediction.main),
              ("Stress", stress.main), ("Restitution", restitution.main)]
    if "--sans-sources" not in sys.argv:
        etapes = [("Extraction marché", extract_marche.main),
                  ("Extraction filiales", generer_flux_filiales.main)] + etapes
    for nom, etape in etapes:
        debut = time.time()
        print(f"\n=== {nom} ===")
        etape()
        print(f"--- {nom} terminé en {time.time() - debut:.1f}s")


if __name__ == "__main__":
    main()
