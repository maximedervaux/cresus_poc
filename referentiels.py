"""Référentiel des types de flux et tables de correspondance par filiale.

Chaque système source utilise ses propres libellés : ces tables constituent le
mapping "source -> référentiel Groupe" appliqué par l'ETL.
"""

# Référentiel Groupe : code -> sens
# ENCAISSEMENT : flux entrants (positifs pour la banque)
# DECAISSEMENT : flux sortants (négatifs pour la banque)
TYPES_FLUX = {
    "REPORT_A_NOUVEAU": "ENCAISSEMENT",       # solde d'ouverture
    "DEPOTS_CLIENTS": "ENCAISSEMENT",
    "REMBOURSEMENTS_CREDITS": "ENCAISSEMENT",
    "COMMISSIONS": "ENCAISSEMENT",
    "INTERETS_RECUS": "ENCAISSEMENT",
    "RETRAITS_CLIENTS": "DECAISSEMENT",
    "OCTROI_CREDITS": "DECAISSEMENT",
    "SALAIRES": "DECAISSEMENT",
    "FRAIS_GENERAUX": "DECAISSEMENT",
    "INTERETS_VERSES": "DECAISSEMENT",
    "IMPOTS": "DECAISSEMENT",
}

# France : libellés français
LIB_FR = {
    "REPORT_A_NOUVEAU": "Report à nouveau",
    "DEPOTS_CLIENTS": "Dépôts clients",
    "REMBOURSEMENTS_CREDITS": "Remboursements de crédits",
    "COMMISSIONS": "Commissions perçues",
    "INTERETS_RECUS": "Intérêts reçus",
    "RETRAITS_CLIENTS": "Retraits clients",
    "OCTROI_CREDITS": "Décaissements de crédits",
    "SALAIRES": "Salaires et charges",
    "FRAIS_GENERAUX": "Frais généraux",
    "INTERETS_VERSES": "Intérêts versés",
    "IMPOTS": "Impôts et taxes",
}

# Canada : libellés anglais
LIB_CA = {
    "REPORT_A_NOUVEAU": "Opening balance",
    "DEPOTS_CLIENTS": "Customer deposits",
    "REMBOURSEMENTS_CREDITS": "Loan repayments",
    "COMMISSIONS": "Fees & commissions",
    "INTERETS_RECUS": "Interest received",
    "RETRAITS_CLIENTS": "Customer withdrawals",
    "OCTROI_CREDITS": "Loan disbursements",
    "SALAIRES": "Payroll",
    "FRAIS_GENERAUX": "Operating expenses",
    "INTERETS_VERSES": "Interest paid",
    "IMPOTS": "Taxes",
}

# Côte d'Ivoire : codes courts
CODE_CI = {
    "REPORT_A_NOUVEAU": "RAN",
    "DEPOTS_CLIENTS": "DEP_CLI",
    "REMBOURSEMENTS_CREDITS": "REMB_CRED",
    "COMMISSIONS": "COMM",
    "INTERETS_RECUS": "INT_REC",
    "RETRAITS_CLIENTS": "RET_CLI",
    "OCTROI_CREDITS": "OCT_CRED",
    "SALAIRES": "SAL",
    "FRAIS_GENERAUX": "FG",
    "INTERETS_VERSES": "INT_VERS",
    "IMPOTS": "IMP",
}
