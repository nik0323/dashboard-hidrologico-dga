"""Smoke test de la app completa con streamlit.testing (datos sintéticos, sin archivos DGA reales)."""

import re
import warnings

import pytest
from streamlit.testing.v1 import AppTest

from casos import csv_caudales, csv_calidad, csv_pozos, csv_precipitaciones, escribir_agromet
from hidro.config import RAIZ_PROYECTO, cargar_settings

MODULOS = ["Precipitaciones", "Parámetros de Cuenca (HEC-HMS)", "Caudales", "Aguas Subterráneas", "Calidad Geoquímica"]


@pytest.fixture
def dir_datos(tmp_path, monkeypatch):
    archivos = cargar_settings().archivos
    # 14 años con 5 % de vacíos: suficientes años completos para el ajuste (hallazgo #4)
    precip = csv_precipitaciones(inicio_cercana="2000-01-01", fin_cercana="2013-12-31", faltantes=0.05)
    contenidos = {"precipitaciones": precip, "caudales": csv_caudales(),
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
    assert at.selectbox(key="precipitaciones__dist__ESTACION CERCANA").value in ("Gumbel", "Log-Pearson III", "Log-Normal")
    assert at.checkbox(key="precipitaciones__usar_agromet").value is True


def _p24_mostrado(at):
    """(P24, factor, PMA diaria) del recuadro informativo y suma del hietograma HEC-HMS."""
    texto = next(i.value for i in at.info if "Precipitación Base" in i.value)
    p24, factor, p_diaria = map(float, re.search(r"\*\*([\d.]+) mm\*\* = ([\d.]+) × ([\d.]+) mm", texto).groups())
    suma_hec = at.dataframe[-1].value["Precipitación Incremental (mm)"].sum()
    return p24, factor, p_diaria, suma_hec


def test_hallazgo7_tormenta_usa_p24_movil(dir_datos):
    at = _ejecutar("Precipitaciones")
    p24, factor, p_diaria, suma_hec = _p24_mostrado(at)
    assert factor == 1.13
    assert p24 == pytest.approx(1.13 * p_diaria, abs=0.012)       # valores mostrados con 2 decimales
    assert suma_hec == pytest.approx(p24, abs=0.06)                # 96 bloques redondeados a 3 decimales

    at.number_input(key="precipitaciones__factor_if").set_value(1.0).run()
    p24, factor, p_diaria, _ = _p24_mostrado(at)
    assert factor == 1.0 and p24 == p_diaria                       # factor 1 = dashboard original


def test_hallazgo10_tormenta_usa_distribucion_recomendada(dir_datos):
    from hidro.core import frecuencia
    from hidro.core.estaciones import filtrar_por_radio, serie_estacion
    from hidro.core.series import maximos_anuales
    from hidro.io.imputacion import imputar_con_agromet
    from hidro.io.lectura import cargar_agromet, cargar_serie_dga

    s = cargar_settings()
    df = cargar_serie_dga(str(dir_datos / s.archivos["precipitaciones"]), "PRECIPIT")
    fr = filtrar_por_radio(df, s.punto_control.lat, s.punto_control.lon, 30, "NOMBRE ESTACION")
    agro, _ = cargar_agromet(str(dir_datos), s.patron_agromet, s.qa_max_precip_horaria_mm)
    serie = imputar_con_agromet(serie_estacion(fr.df_radio, "NOMBRE ESTACION", "ESTACION CERCANA"), agro,
                                cobertura_min_anual=s.cobertura_min_anual)
    aj = frecuencia.ajustar_distribuciones(maximos_anuales(serie, s.cobertura_min_maximos)["Valor_Registrado"],
                                           s.t_objetivo, s.n_min_ajuste)
    esperada = frecuencia.distribucion_recomendada(aj, frecuencia.diagnosticar_cola(aj, s.t_cola, s.crecimiento_min_cola))

    at = _ejecutar("Precipitaciones")
    assert at.selectbox(key="precipitaciones__dist__ESTACION CERCANA").value == esperada
    assert any(f"Distribución recomendada para diseño: **{esperada}**" in x.value for x in at.caption)


def _texto_giandotti(at):
    return next(i.value for i in at.info if "Giandotti" in i.value)


def test_hallazgo3_giandotti_pide_altura_media_y_la_usa(dir_datos):
    at = _ejecutar("Parámetros de Cuenca (HEC-HMS)")
    assert "ingrese la altitud media" in _texto_giandotti(at)       # sin valores inventados por defecto

    at.number_input(key="cuenca__altitud_media").set_value(650.0)
    at.number_input(key="cuenca__cota_salida").set_value(450.0).run()
    esperado = (4 * 15.5 ** 0.5 + 1.5 * 8.2) / (0.8 * 200.0 ** 0.5)   # A, L por defecto; H = 200 m
    assert f"{esperado:.2f} horas (H = 200 m)" in _texto_giandotti(at)
    assert not at.error

    at.number_input(key="cuenca__cota_salida").set_value(700.0).run()
    assert any("mayor que la cota de la salida" in e.value for e in at.error)


def test_cuenca_tabla_invalida_no_genera_ficha(dir_datos):
    at = _ejecutar("Parámetros de Cuenca (HEC-HMS)")
    assert len(at.table) == 1  # ficha HEC-HMS con la tabla de ejemplo válida
    at.number_input(key="cuenca__tc_adoptado").set_value(2.0).run()
    assert not at.exception
