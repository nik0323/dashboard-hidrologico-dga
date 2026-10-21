"""Red de seguridad: el original congelado sigue produciendo las salidas guardadas en golden/.

En la Fase 3 se agrega el mismo contraste para el paquete `hidro` contra estas salidas.
"""

import hashlib
import os

import pandas as pd
import pytest

from casos import CASOS, DIR_ORIGINAL, RUTA_GOLDEN, api_original, comparar

SHA256_ORIGINAL = "742D7F15B312A4803D4B2FDFC62A5984D45574C146D59828A5A3EB7F4E98506A"


@pytest.fixture(scope="module")
def api():
    return api_original()


@pytest.fixture(scope="module")
def golden():
    return pd.read_pickle(RUTA_GOLDEN)


def test_original_congelado_no_modificado():
    with open(os.path.join(DIR_ORIGINAL, "dashboard_dga_original.py"), "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest().upper() == SHA256_ORIGINAL


def test_golden_cubre_todos_los_casos(golden):
    assert sorted(golden) == sorted(CASOS)


@pytest.mark.parametrize("nombre", list(CASOS))
def test_original_reproduce_golden(api, golden, nombre):
    comparar(CASOS[nombre](api), golden[nombre], nombre)
