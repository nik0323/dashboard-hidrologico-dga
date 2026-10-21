"""Congela salidas de referencia.

    python tests/generar_golden.py            # original -> golden/salidas_original.pkl
    python tests/generar_golden.py --hidro    # paquete  -> golden/salidas_hidro.pkl

El golden del original no debería regenerarse nunca (el original está congelado). El de hidro
se regenera solo al implementar un cambio numérico aprobado, registrándolo en
`cambios_aprobados.py`.
"""

import os
import sys

import pandas as pd

from casos import CASOS, RUTA_GOLDEN, RUTA_GOLDEN_HIDRO, api_original


def main():
    if "--hidro" in sys.argv:
        from adaptador_hidro import api_hidro
        api, ruta = api_hidro(), RUTA_GOLDEN_HIDRO
    else:
        api, ruta = api_original(), RUTA_GOLDEN
    salidas = {nombre: fn(api) for nombre, fn in CASOS.items()}
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    pd.to_pickle(salidas, ruta)
    print(f"{len(salidas)} casos guardados en {ruta}")


if __name__ == "__main__":
    main()
