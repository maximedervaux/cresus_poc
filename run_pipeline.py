"""Orchestration : à planifier quotidiennement (cron / Planificateur).

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
    # On définit la liste des étapes à exécuter, avec leur nom et la fonction correspondante
    etapes = [("ETL", etl.main), ("Prédiction", prediction.main),
              ("Stress", stress.main), ("Restitution", restitution.main)]

    # Si l'option --sans-sources n'est pas passée, on commence par extraire les fichiers sources
    if "--sans-sources" not in sys.argv:
        etapes = [("Extraction marché", extract_marche.main),
                  ("Extraction filiales", generer_flux_filiales.main)] + etapes

    # On exécute les étapes dans l'ordre
    for nom, etape in etapes:
        debut = time.time()
        print(f"\n=== {nom} ===")
        etape()
        print(f"--- {nom} terminé en {time.time() - debut:.1f}s")


if __name__ == "__main__":
    main()
