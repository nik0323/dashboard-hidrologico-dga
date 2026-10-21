"""El paquete `hidro` reproduce las salidas congeladas del original (tolerancia 1e-9)."""

import subprocess
import sys

import pandas as pd
import pytest

from adaptador_hidro import api_hidro
from casos import CASOS, RUTA_GOLDEN, comparar


@pytest.fixture(scope="module")
def api():
    return api_hidro()


@pytest.fixture(scope="module")
def golden():
    return pd.read_pickle(RUTA_GOLDEN)


@pytest.mark.parametrize("nombre", list(CASOS))
def test_hidro_reproduce_golden(api, golden, nombre):
    comparar(CASOS[nombre](api), golden[nombre], nombre)


@pytest.mark.parametrize("paquete", ["hidro.core", "hidro.io"])
def test_logica_no_importa_streamlit(paquete):
    codigo = (f"import sys, pkgutil, importlib, {paquete} as p\n"
              f"[importlib.import_module(f'{paquete}.{{m.name}}') for m in pkgutil.iter_modules(p.__path__)]\n"
              "print('streamlit' in sys.modules)")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert salida.stdout.strip() == "False"
