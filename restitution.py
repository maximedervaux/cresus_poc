"""Restitution : création des vues SQL consommées par Power BI (MOE §2.2.5)."""
from config import SQL_DIR
from db import executer_script_sql


def main():
    executer_script_sql(SQL_DIR / "vues.sql")
    print("[restitution] vues v_* créées dans cresus_poc")


if __name__ == "__main__":
    main()
