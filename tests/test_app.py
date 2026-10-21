"""Smoke test de la app completa con streamlit.testing (datos sintéticos, sin archivos DGA reales)."""

import warnings

import pytest
from streamlit.testing.v1 import AppTest

from casos import csv_caudales, csv_calidad, csv_pozos, csv_precipitaciones, escribir_agromet
from hidro.config import RAIZ_PROYECTO, cargar_settings

MODULOS = ["Precipitaciones", "Parámetros de Cuenca (HEC-HMS)", "Caudales", "Aguas Subterráneas", "Calidad Geoquímica"]


@pytest.fixture
def dir_datos(tmp_path, monkeypatch):
    archivos = cargar_settings().archivos
    contenidos = {"precipitaciones": csv_precipitaciones(), "caudales": csv_caudales(),
                  "pozos": csv_pozos(), "calidad": csv_calidad()}
    for clave, contenido in contenidos.items():
        (tmp_path / archivos[clave]).write_bytes(contenido)
    escribir_agromet(tmp_path)
    monkeypatch.setenv("DGA_DATA_DIR", str(tmp_path))
    return tmp_path


def _ejecutar(modulo):
    at = AppTest.from_file(str(RAIZ_PROYECTO / "app.py"), default_timeout=120)
    at.run()
    at.sidebar.radio(key="app__modulo").set_value(modulo).run()
    return at


@pytest.mark.parametrize("modulo", MODULOS)
def test_modulo_renderiza_sin_errores(dir_datos, modulo):
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        at = _ejecutar(modulo)
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    obsoletos = [str(w.message) for w in avisos if issubclass(w.category, DeprecationWarning)
                 and ("plotly" in str(w.filename) or "streamlit" in str(w.filename))]
    assert not obsoletos, obsoletos


def test_precipitaciones_muestra_cuantiles_y_hietograma(dir_datos):
    at = _ejecutar("Precipitaciones")
    textos = " ".join(m.value for m in at.markdown) + " ".join(i.value for i in at.info)
    assert "Precipitación Base" in textos
    assert at.selectbox(key="precipitaciones__dist").value in ("Gumbel", "Log-Pearson III", "Log-Normal")
    assert at.checkbox(key="precipitaciones__usar_agromet").value is True


def test_cuenca_tabla_invalida_no_genera_ficha(dir_datos):
    at = _ejecutar("Parámetros de Cuenca (HEC-HMS)")
    assert len(at.table) == 1  # ficha HEC-HMS con la tabla de ejemplo válida
    at.number_input(key="cuenca__tc_adoptado").set_value(2.0).run()
    assert not at.exception
