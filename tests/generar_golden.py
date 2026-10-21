"""Congela las salidas del original en tests/golden/salidas_original.pkl.

Uso (solo cuando se apruebe un cambio numérico o se agreguen casos):
    python tests/generar_golden.py
"""

import os

import pandas as pd

from casos import CASOS, RUTA_GOLDEN, api_original


def main():
    api = api_original()
    salidas = {nombre: fn(api) for nombre, fn in CASOS.items()}
    os.makedirs(os.path.dirname(RUTA_GOLDEN), exist_ok=True)
    pd.to_pickle(salidas, RUTA_GOLDEN)
    print(f"{len(salidas)} casos guardados en {RUTA_GOLDEN}")


if __name__ == "__main__":
    main()
