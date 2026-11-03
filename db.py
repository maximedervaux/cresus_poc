"""Accès à la base MySQL cresus_poc."""
import re

from sqlalchemy import create_engine

from config import DB_SERVER_URL, DB_URL


def get_engine():
    return create_engine(DB_URL)


def executer_script_sql(chemin, sur_serveur=False):
    """Exécute un fichier .sql (instructions séparées par « ; » en fin de ligne)."""
    texte = "\n".join(l for l in chemin.read_text(encoding="utf-8").splitlines()
                      if not l.strip().startswith("--"))
    instructions = [s.strip() for s in re.split(r";\s*$", texte, flags=re.M) if s.strip()]
    engine = create_engine(DB_SERVER_URL if sur_serveur else DB_URL)
    with engine.begin() as conn:
        for instruction in instructions:
            conn.exec_driver_sql(instruction.replace("%", "%%"))  # % littéral pour pymysql
