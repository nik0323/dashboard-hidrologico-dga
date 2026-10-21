"""Smoke test de la app completa con streamlit.testing (datos sintéticos, sin archivos DGA reales)."""

import re
import warnings

import pytest
from streamlit.testing.v1 import AppTest

from casos import csv_caudales, csv_calidad, csv_pozos, csv_precipitaciones, escribir_agromet
from hidro.config import RAIZ_PROYECTO, cargar_settings

MODULOS = ["Precipitaciones", "Parámetros de Cuenca (HEC-HMS)", "Caudales", "Aguas Subterráneas", "Calidad Geoquímica",
           "Normas de Calidad (NCh 409 / 1333)"]


def _calidad_con_marcas():
    """Datos de calidad con marca DGA: en Sulfato, 1 de cada 3 muestras '<' (límite de detección), el resto '='."""
    lineas, n_sulfato = [], 0
    for linea in csv_calidad().decode("utf-8").splitlines():
        if ",Sulfato,7350," in linea and ", ,mg/l" in linea:
            marca = "<" if n_sulfato % 3 == 0 else "="
            linea = linea.replace(", ,mg/l", f",{marca},mg/l")
            n_sulfato += 1
        lineas.append(linea)
    return ("\n".join(lineas) + "\n").encode("utf-8")


FILA_POZO = "06019001,ESTACION CERCANA,6,X,PLACILLA,0343810  ,0710126  ,0,0,210,{fecha},{nivel},{obs},m"
POZOS_EXTRA = [("15/06/2016", "80.0", "Dinamico"), ("15/07/2016", "", "Seco"), ("15/08/2016", "0", "Embancado")]


def _pozos_con_observaciones():
    """Pozos sintéticos + en ESTACION CERCANA una medición dinámica profunda, una seca y una embancada en 0 m."""
    extra = "\n".join(FILA_POZO.format(fecha=f, nivel=n, obs=o) for f, n, o in POZOS_EXTRA)
    return csv_pozos() + (extra + "\n").encode("utf-8")


@pytest.fixture
def dir_datos(tmp_path, monkeypatch):
    archivos = cargar_settings().archivos
    # 14 años con 5 % de vacíos: suficientes años completos para el ajuste (hallazgo #4)
    precip = csv_precipitaciones(inicio_cercana="2000-01-01", fin_cercana="2013-12-31", faltantes=0.05)
    contenidos = {"precipitaciones": precip, "caudales": csv_caudales(),
                  "pozos": _pozos_con_observaciones(), "calidad": _calidad_con_marcas()}
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


def test_hallazgo8_aviso_qma_medio_diario(dir_datos):
    at = _ejecutar("Caudales")
    assert any("caudales **medios diarios**" in w.value for w in at.warning)


def test_hallazgo11_calidad_separa_censurados(dir_datos):
    at = _ejecutar("Calidad Geoquímica")
    at.selectbox(key="calidad__parametro").set_value("Sulfato").run()
    assert not at.exception
    aviso = next(w.value for w in at.warning if "censuradas" in w.value)
    n_cens, n_total = map(int, re.match(r"(\d+) de (\d+) muestras", aviso).groups())
    assert n_cens > 0 and n_cens < n_total
    resumen = at.dataframe[0].value.set_index("Marca")
    assert resumen.loc["Bajo límite de detección (<)", "Muestras"] == n_cens
    assert resumen["Muestras"].sum() == n_total

    at.selectbox(key="calidad__parametro").set_value("Ph").run()   # sin marcas '<': sin aviso
    assert not any("censuradas" in w.value for w in at.warning)


def test_normas_evalua_y_advierte_limites_sin_verificar(dir_datos):
    at = _ejecutar("Normas de Calidad (NCh 409 / 1333)")
    assert any("NO están verificados" in w.value for w in at.warning)
    at.selectbox(key="normas__norma").set_value("nch1333_riego").run()
    assert not at.exception
    resumen = at.dataframe[0].value.set_index("Parámetro")
    # Sulfato sintético ≈ 120 ± 25 mg/l (límite 250); 1 de cada 3 muestras '<' con LD = valor registrado
    assert resumen.loc["Sulfato", "Estado"] == "Cumple"
    assert resumen.loc["Sulfato", "Determinadas"] == resumen.loc["Sulfato", "Muestras"]
    assert resumen.loc["pH", "Estado"] == "Cumple"
    assert resumen.loc["Bario", "Estado"] == "Sin parámetro DGA"


def test_hallazgo12_pozos_usa_solo_niveles_estaticos(dir_datos):
    from hidro.core.series import rango_niveles
    from hidro.io.lectura import cargar_serie_dga

    base = cargar_serie_dga(csv_pozos(), "NIVEL")                  # sin las mediciones agregadas
    esperado = rango_niveles(base[base["NOMBRE ESTACION"] == "ESTACION CERCANA"])

    at = _ejecutar("Aguas Subterráneas")
    assert not at.exception and at.selectbox(key="pozos__estacion").value == "ESTACION CERCANA"
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Abatimiento Máximo"] == f"{esperado.nivel_max:.2f} m"     # no 80 m (dinámico)
    assert metricas["Nivel Somero Máximo"] == f"{esperado.nivel_min:.2f} m"    # no 0 m (embancado)
    assert any("1 dinámicas (con bombeo) y 1 con pozo embancado" in w.value for w in at.warning)
    assert any("1 visitas con el pozo **seco**" in i.value and "2016" in i.value for i in at.info)


def test_cuenca_tabla_invalida_no_genera_ficha(dir_datos):
    at = _ejecutar("Parámetros de Cuenca (HEC-HMS)")
    assert len(at.table) == 1  # ficha HEC-HMS con la tabla de ejemplo válida
    at.number_input(key="cuenca__tc_adoptado").set_value(2.0).run()
    assert not at.exception
