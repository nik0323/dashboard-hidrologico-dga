"""El paquete `hidro` reproduce sus salidas congeladas (tolerancia 1e-9) y solo difiere del
original en los casos registrados en `cambios_aprobados.py`."""

import subprocess
import sys

import pandas as pd
import pytest

from adaptador_hidro import api_hidro
from cambios_aprobados import CAMBIOS_APROBADOS
from casos import CASOS, RUTA_GOLDEN, RUTA_GOLDEN_HIDRO, comparar


@pytest.fixture(scope="module")
def api():
    return api_hidro()


@pytest.fixture(scope="module")
def golden_hidro():
    return pd.read_pickle(RUTA_GOLDEN_HIDRO)


@pytest.mark.parametrize("nombre", list(CASOS))
def test_hidro_reproduce_golden(api, golden_hidro, nombre):
    comparar(CASOS[nombre](api), golden_hidro[nombre], nombre)


def _difiere(a, b):
    try:
        comparar(a, b)
        return False
    except AssertionError:
        return True


def test_solo_difiere_del_original_en_cambios_aprobados(golden_hidro):
    golden_original = pd.read_pickle(RUTA_GOLDEN)
    assert sorted(golden_hidro) == sorted(golden_original)
    difieren = {k for k in golden_original if _difiere(golden_hidro[k], golden_original[k])}
    assert difieren == set(CAMBIOS_APROBADOS), (
        f"No registrados: {sorted(difieren - set(CAMBIOS_APROBADOS))}; "
        f"registrados sin efecto: {sorted(set(CAMBIOS_APROBADOS) - difieren)}")


@pytest.mark.parametrize("paquete", ["hidro.core", "hidro.io"])
def test_logica_no_importa_streamlit(paquete):
    codigo = (f"import sys, pkgutil, importlib, {paquete} as p\n"
              f"[importlib.import_module(f'{paquete}.{{m.name}}') for m in pkgutil.iter_modules(p.__path__)]\n"
              "print('streamlit' in sys.modules)")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert salida.stdout.strip() == "False"
