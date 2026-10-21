"""Propiedades de las correcciones aprobadas (ver cambios_aprobados.py)."""

import numpy as np
import pandas as pd
import pytest

from casos import RUTA_GOLDEN, _agromet, _serie_precip, api_original, comparar
from hidro.config import cargar_settings
from hidro.io.imputacion import anios_bajo_cobertura, cobertura_anual, imputar_con_agromet


@pytest.fixture(scope="module")
def entradas():
    api = api_original()
    df_agro, _ = _agromet(api)
    dga = pd.DataFrame({
        "FECHA_DT": pd.to_datetime(["2020-01-01 08:00", "2020-01-01 20:00", "2020-01-03 00:00", "2020-01-06 08:00"]),
        "Valor_Registrado": [2.0, 4.0, 0.0, 10.0],
    })
    agro = pd.DataFrame({"FECHA_DT": pd.date_range("2019-12-30", "2020-01-08"), "Precip_mm": np.arange(10, dtype=float)})
    return {"pipeline": (_serie_precip(api), df_agro), "sintetico": (dga, agro)}


# ---------- Hallazgo #1: no extender fuera del periodo DGA (cobertura desactivada) ----------
def test_hallazgo1_sin_restricciones_reproduce_original(entradas):
    golden = pd.read_pickle(RUTA_GOLDEN)["imputar_con_agromet"]
    for nombre, (dga, agro) in entradas.items():
        comparar(imputar_con_agromet(dga, agro, extender=True, cobertura_min_anual=0.0), golden[nombre], nombre)


def test_hallazgo1_solo_rellena_vacios_internos(entradas):
    for dga, agro in entradas.values():
        out = imputar_con_agromet(dga, agro, cobertura_min_anual=0.0)
        dias_dga = dga["FECHA_DT"].dt.normalize()
        assert out["FECHA_DT"].min() == dias_dga.min()
        assert out["FECHA_DT"].max() == dias_dga.max()
        # los días con registro DGA conservan su valor (promedio diario) y no se marcan imputados
        medias = dga.groupby(dias_dga)["Valor_Registrado"].mean()
        con_dga = out.set_index("FECHA_DT").loc[medias.index]
        np.testing.assert_allclose(con_dga["Valor_Registrado"], medias.values, rtol=0, atol=1e-12)
        assert not con_dga["IMPUTADO"].any()
        assert out["IMPUTADO"].sum() == len(out) - len(medias)


def test_hallazgo1_caso_sintetico_explicito(entradas):
    out = imputar_con_agromet(*entradas["sintetico"], cobertura_min_anual=0.0)
    # DGA: 01/01 (media 3), 03/01, 06/01; AGROMET rellena 02, 04 y 05/01 con 3, 5 y 6 mm
    assert out["FECHA_DT"].dt.strftime("%d/%m").tolist() == ["01/01", "02/01", "03/01", "04/01", "05/01", "06/01"]
    assert out["Valor_Registrado"].tolist() == [3.0, 3.0, 0.0, 5.0, 6.0, 10.0]
    assert out["IMPUTADO"].tolist() == [False, True, False, True, True, False]


# ---------- Hallazgo #1b: no imputar años con cobertura DGA < umbral ----------
@pytest.fixture(scope="module")
def serie_cobertura_mixta():
    """2019: falta 1 mes (91.8 %); 2020: solo 100 días (27.3 %); 2021: faltan 10 días (97.3 %)."""
    dias = pd.date_range("2019-01-01", "2021-12-31")
    hueco_2019 = (dias >= "2019-06-01") & (dias <= "2019-06-30")
    hueco_2020 = (dias.year == 2020) & (dias > "2020-04-09")
    hueco_2021 = (dias >= "2021-07-01") & (dias <= "2021-07-10")
    con_dato = dias[~(hueco_2019 | hueco_2020 | hueco_2021)]
    dga = pd.DataFrame({"FECHA_DT": con_dato, "Valor_Registrado": 1.0})
    agro = pd.DataFrame({"FECHA_DT": dias, "Precip_mm": 7.0})
    return dga, agro


def test_cobertura_anual(serie_cobertura_mixta):
    cob = cobertura_anual(serie_cobertura_mixta[0])
    np.testing.assert_allclose(cob.to_numpy(), [335 / 365, 100 / 366, 355 / 365], rtol=0, atol=1e-15)
    assert cob.index.tolist() == [2019, 2020, 2021]


def test_hallazgo1b_no_imputa_anios_bajo_cobertura(serie_cobertura_mixta):
    dga, agro = serie_cobertura_mixta
    out = imputar_con_agromet(dga, agro, cobertura_min_anual=0.80)
    imputados = out[out["IMPUTADO"]].groupby(out["FECHA_DT"].dt.year).size().to_dict()
    assert imputados == {2019: 30, 2021: 10}
    assert (out["FECHA_DT"].dt.year == 2020).sum() == 100        # 2020 queda solo con días DGA
    assert (out.loc[out["IMPUTADO"], "Valor_Registrado"] == 7.0).all()
    assert (out.loc[~out["IMPUTADO"], "Valor_Registrado"] == 1.0).all()
    assert anios_bajo_cobertura(dga, agro, 0.80) == [2020]


def test_hallazgo1b_umbral_cero_equivale_a_hallazgo1(serie_cobertura_mixta):
    dga, agro = serie_cobertura_mixta
    out = imputar_con_agromet(dga, agro, cobertura_min_anual=0.0)
    assert out["IMPUTADO"].sum() == 30 + (366 - 100) + 10
    assert anios_bajo_cobertura(dga, agro, 0.0) == []


def test_hallazgo1b_umbral_configurado():
    assert cargar_settings().cobertura_min_anual == 0.80


# ---------- Hallazgo #4: máximos anuales solo de años con cobertura >= umbral ----------
def _serie_diaria(dias, valores):
    from hidro.io.normalizacion import agregar_columnas_fecha
    return agregar_columnas_fecha(pd.DataFrame({"FECHA_DT": dias, "Valor_Registrado": valores}))


def test_hallazgo4_excluye_anios_incompletos(serie_cobertura_mixta):
    from hidro.core.series import anios_incompletos, maximos_anuales
    dga, _ = serie_cobertura_mixta
    df = _serie_diaria(dga["FECHA_DT"], np.arange(len(dga), dtype=float))
    pma = maximos_anuales(df, 0.80)
    assert pma["AÑO"].tolist() == [2019, 2021]                      # 2020 (27.3 %) excluido
    assert anios_incompletos(df, 0.80) == [2020]
    original = df.groupby("AÑO")["Valor_Registrado"].max().reset_index()
    pd.testing.assert_frame_equal(maximos_anuales(df, 0.0), original)  # umbral 0 = original
    pd.testing.assert_frame_equal(pma, original[original["AÑO"] != 2020].reset_index(drop=True))


def test_hallazgo4_umbral_exacto_y_bisiesto():
    from hidro.core.series import maximos_anuales
    # 2020 bisiesto: 293/366 = 0.8005 (entra); 2021: 291/365 = 0.7973 (sale); 2022: 292/365 = 0.8 (entra)
    dias = pd.DatetimeIndex(list(pd.date_range("2020-01-01", periods=293))
                            + list(pd.date_range("2021-01-01", periods=291))
                            + list(pd.date_range("2022-01-01", periods=292)))
    pma = maximos_anuales(_serie_diaria(dias, 1.0), 0.80)
    assert pma["AÑO"].tolist() == [2020, 2022]


def test_hallazgo4_cuenta_dias_distintos():
    from hidro.core.series import cobertura_anual
    # mediciones repetidas el mismo día no inflan la cobertura
    dias = pd.DatetimeIndex(list(pd.date_range("2021-01-01", periods=100)) * 3)
    assert cobertura_anual(_serie_diaria(dias, 1.0)).loc[2021] == pytest.approx(100 / 365)


def test_hallazgo4_umbral_configurado():
    assert cargar_settings().cobertura_min_maximos == 0.80


# ---------- Hallazgo #7: P24 de 24 h móviles = factor · PMA diaria de intervalo fijo ----------
def test_hallazgo7_p24_movil():
    from hidro.core.tormentas import FACTOR_INTERVALO_FIJO_DEFECTO, hietograma_bloques_alternos, p24_movil
    assert FACTOR_INTERVALO_FIJO_DEFECTO == 1.13
    assert p24_movil(100.0) == pytest.approx(113.0, abs=1e-12)
    assert p24_movil(87.3, 1.0) == 87.3                      # factor 1 = dashboard original
    _, hieto = hietograma_bloques_alternos(p24_movil(87.3), 15, 24, 0.33)
    assert hieto.sum() == pytest.approx(1.13 * 87.3, abs=1e-9)


# ---------- Hallazgo #10: diagnóstico de cola y distribución recomendada ----------
SERIE_CON_TECHO = np.array([70.0, 69.0, 68.0, 66.0, 40.0])   # n = 5, asimetría de log10 negativa fuerte


def test_hallazgo10_detecta_techo_lp3():
    from hidro.core.frecuencia import ajustar_distribuciones, diagnosticar_cola, distribucion_recomendada
    aj = ajustar_distribuciones(SERIE_CON_TECHO)
    diag = diagnosticar_cola(aj)
    assert aj.mejor == "Log-Pearson III"                     # menor D de KS (se sigue informando)
    assert diag["Log-Pearson III"].con_techo
    assert not diag["Gumbel"].con_techo
    sin_techo = [d for d in aj.ks["Distribución"] if not diag[d].con_techo]
    assert distribucion_recomendada(aj, diag) == sin_techo[0]
    # la cota de LP-III acota todos sus cuantiles y coincide con 10^(μ − 2σ/g)
    from scipy.stats import skew
    lx = np.log10(SERIE_CON_TECHO)
    cota = 10 ** (lx.mean() - 2 * lx.std(ddof=1) / skew(lx, bias=False))
    assert aj.lp3_cota_superior == pytest.approx(cota, rel=1e-12)
    assert max(aj.cuantiles["Log-Pearson III"].values()) <= aj.lp3_cota_superior


def test_hallazgo10_sin_techo_recomienda_menor_d():
    from casos import SERIES_PMA
    from hidro.core.frecuencia import ajustar_distribuciones, diagnosticar_cola, distribucion_recomendada
    aj = ajustar_distribuciones(SERIES_PMA["gumbel_30"](np.random.default_rng(2)))
    diag = diagnosticar_cola(aj)
    assert not any(d.con_techo for d in diag.values())
    assert distribucion_recomendada(aj, diag) == aj.mejor
    assert diag["Gumbel"].crecimiento == pytest.approx(aj.cuantiles["Gumbel"][500] / aj.cuantiles["Gumbel"][50] - 1)


def test_hallazgo10_todas_con_techo_recomienda_menor_d():
    from casos import SERIES_PMA
    from hidro.core.frecuencia import ajustar_distribuciones, diagnosticar_cola, distribucion_recomendada
    aj = ajustar_distribuciones(SERIES_PMA["gumbel_30"](np.random.default_rng(2)))
    diag = diagnosticar_cola(aj, crecimiento_min=0.99)
    assert all(d.con_techo for d in diag.values())
    assert distribucion_recomendada(aj, diag) == aj.mejor


def test_hallazgo10_cota_infinita_con_asimetria_positiva():
    from casos import SERIES_PMA
    from hidro.core.frecuencia import ajustar_distribuciones
    aj = ajustar_distribuciones(SERIES_PMA["lognormal_50"](np.random.default_rng(2)))
    lx = np.log10(SERIES_PMA["lognormal_50"](np.random.default_rng(2)))
    from scipy.stats import skew
    assert (skew(lx, bias=False) >= 0) == np.isinf(aj.lp3_cota_superior)


def test_hallazgo10_configurado():
    s = cargar_settings()
    assert (s.t_cola, s.crecimiento_min_cola) == ((50, 500), 0.05)


# ---------- Hallazgo #3: Giandotti con H = altitud media de la cuenca − cota de salida ----------
def test_hallazgo3_giandotti_usa_altura_media():
    from hidro.core import cuenca
    geom = cuenca.geometria_desde_desnivel(8.2, 369.0)
    h = cuenca.altura_media_sobre_salida(650.0, 450.0)
    assert h == 200.0
    tcs = cuenca.tiempos_concentracion(15.5, 8.2, geom, h)
    assert tcs.giandotti == pytest.approx((4 * np.sqrt(15.5) + 1.5 * 8.2) / (0.8 * np.sqrt(200.0)), rel=1e-15)
    # Kirpich y California no dependen de H
    original = cuenca.tiempos_concentracion(15.5, 8.2, geom, geom.desnivel_m)
    assert (tcs.kirpich, tcs.california) == (original.kirpich, original.california)
    # tc ∝ 1/√H: con H menor que el desnivel del cauce, Giandotti aumenta
    assert tcs.giandotti / original.giandotti == pytest.approx(np.sqrt(369.0 / 200.0), rel=1e-12)


def test_hallazgo3_sin_altura_omite_giandotti():
    from hidro.core import cuenca
    tcs = cuenca.tiempos_concentracion(15.5, 8.2, cuenca.geometria_desde_pendiente(8.2, 0.045), None)
    assert tcs.giandotti is None
    assert len(tcs.como_array()) == 2
    assert tcs.dispersion_excesiva() == bool(max(tcs.kirpich, tcs.california) / min(tcs.kirpich, tcs.california) > 3)


@pytest.mark.parametrize("media, salida", [(450.0, 450.0), (400.0, 450.0)])
def test_hallazgo3_altura_invalida(media, salida):
    from hidro.core import cuenca
    with pytest.raises(ValueError):
        cuenca.altura_media_sobre_salida(media, salida)


# ---------- Hallazgo #11: marcas de calidad DGA ----------
def test_hallazgo11_clasifica_marcas_dga():
    from hidro.core.calidad import BAJO_LD, CUANTIFICADO, SIN_MARCA, SOBRE_RANGO, clasificar_marca, resumen_marcas
    df = pd.DataFrame({"CALIDAD": ["=", "<", " ", None, ">", "D", "<"], "VALOR": range(7)})
    cat = clasificar_marca(df)
    assert cat.tolist() == [CUANTIFICADO, BAJO_LD, SIN_MARCA, SIN_MARCA, SOBRE_RANGO, "Otra marca (D)", BAJO_LD]
    r = resumen_marcas(cat).set_index("Marca")
    assert r.loc[BAJO_LD, "Muestras"] == 2 and r.loc[BAJO_LD, "%"] == pytest.approx(28.6)
    assert r["Muestras"].sum() == 7


def test_hallazgo11_sin_columna_calidad():
    from hidro.core.calidad import SIN_MARCA, clasificar_marca
    assert (clasificar_marca(pd.DataFrame({"VALOR": [1.0, 2.0]})) == SIN_MARCA).all()


# ---------- Hallazgo #12: condición de las mediciones de pozos ----------
def test_hallazgo12_clasifica_y_filtra_niveles_estaticos():
    from hidro.core.pozos import (DINAMICO, EMBANCADO, ESTATICO, SECO, SIN_ACCESO, SURGENTE, clasificar_condicion,
                                  niveles_estaticos, resumen_condiciones)
    df = pd.DataFrame({
        "OBSERVACION": [None, "Dinamico", " Seco", "Sin acceso", "Embancado", "Surgente", "", "DINAMICO", "Otro"],
        "Valor_Registrado": [25.0, 80.0, np.nan, np.nan, 0.0, -1.5, 26.0, 75.0, 30.0],
    })
    cond = clasificar_condicion(df)
    assert cond.tolist() == [ESTATICO, DINAMICO, SECO, SIN_ACCESO, EMBANCADO, SURGENTE, ESTATICO, DINAMICO, "Otra (Otro)"]
    assert niveles_estaticos(df)["Valor_Registrado"].tolist() == [25.0, -1.5, 26.0]
    r = resumen_condiciones(df).set_index("Condición")
    assert r.loc[DINAMICO, "Mediciones"] == 2 and r.loc[SECO, "Con nivel"] == 0
    assert r.loc[SURGENTE, "Usada como nivel estático"] and not r.loc[EMBANCADO, "Usada como nivel estático"]


def test_hallazgo12_sin_columna_observacion():
    from hidro.core.pozos import ESTATICO, clasificar_condicion
    assert (clasificar_condicion(pd.DataFrame({"Valor_Registrado": [1.0]})) == ESTATICO).all()


def test_hallazgo12_conservar_filas_sin_valor():
    from hidro.io.lectura import cargar_serie_dga
    csv = ("CODIGO ESTACION,NOMBRE ESTACION,LAT,LONG,Fecha,Nivel,Observacion,Unidad\n"
           "1,P,0343810,0710126,01/01/2020,25.1,,m\n"
           "1,P,0343810,0710126,01/02/2020,,Seco,m\n"
           "1,P,0343810,0710126,32/02/2020,25.0,,m\n").encode("utf-8")
    assert len(cargar_serie_dga(csv, "NIVEL")) == 1                               # comportamiento original
    df = cargar_serie_dga(csv, "NIVEL", conservar_sin_valor=True)
    assert df["OBSERVACION"].fillna("").tolist() == ["", "Seco"]                    # fecha inválida sigue fuera


# ---------- Hallazgos #5 y #6: día pluviométrico AGROMET 08-08 h, faltantes y QA ----------
def _escribir_horario(directorio, lluvias, inicio="2020-01-01 00:00", fin="2020-01-04 23:00", omitir=(), nombre="a"):
    """Archivo AGROMET horario con 0 mm salvo en `lluvias` {timestamp: mm}; `omitir` = horas sin registro."""
    filas = ['"Fecha Hora","Precipitación horaria"']
    for t in pd.date_range(inicio, fin, freq="h"):
        if t in [pd.Timestamp(o) for o in omitir]:
            continue
        filas.append(f'"{t:%d/%m/%Y %H:%M}",{lluvias.get(t.strftime("%Y-%m-%d %H:%M"), 0.0)}')
    (directorio / f"agromet_Placilla {nombre}.csv").write_text("\n".join(filas) + "\n", encoding="utf-8")


def _diario(directorio, **kw):
    from hidro.io.lectura import cargar_agromet
    df, avisos = cargar_agromet(str(directorio), "*agromet_Placilla*.csv", 150.0, **kw)
    return df.set_index("FECHA_DT")["Precip_mm"], avisos


def test_hallazgo5_ventana_08_08(tmp_path):
    # Registro t acumula (t-1h, t]. Día D = (D 08:00, D+1 08:00]
    _escribir_horario(tmp_path, {"2020-01-02 08:00": 1.0,    # cierra la hora 07-08 del 02 -> día 01
                                 "2020-01-02 09:00": 2.0,    # 08-09 del 02 -> día 02
                                 "2020-01-03 08:00": 4.0})   # 07-08 del 03 -> día 02
    d, _ = _diario(tmp_path)
    assert d.index.min() == pd.Timestamp("2020-01-01") and d.index.max() == pd.Timestamp("2020-01-03")
    assert (d.loc["2020-01-01"], d.loc["2020-01-02"], d.loc["2020-01-03"]) == (1.0, 6.0, 0.0)
    # 31/12 (solo 00-08 del 01) y 04/01 (falta 05/01 00-08) quedan incompletos y se descartan
    calendario, _ = _diario(tmp_path, desfase_horas=0)
    assert (calendario.loc["2020-01-02"], calendario.loc["2020-01-03"]) == (3.0, 4.0)   # 00-24 del original


def test_hallazgo6_faltantes_y_qa_no_son_cero(tmp_path):
    _escribir_horario(tmp_path, {"2020-01-02 12:00": 497.0, "2020-01-03 12:00": 5.0},
                      omitir=["2020-01-03 20:00"])
    d, avisos = _diario(tmp_path)
    assert pd.Timestamp("2020-01-02") not in d.index      # hora rechazada por QA -> día incompleto
    assert pd.Timestamp("2020-01-03") not in d.index      # hora faltante -> día incompleto
    assert d.loc["2020-01-01"] == 0.0                     # día completo y seco sigue siendo 0 mm
    assert any("1 registros > 150 mm/h" in a for a in avisos)
    assert any("días AGROMET con menos de 24 h" in a for a in avisos)
    flexible, _ = _diario(tmp_path, horas_min_dia=23)
    assert flexible.loc["2020-01-03"] == 5.0 and flexible.loc["2020-01-02"] == 0.0


def test_hallazgo6_hora_repetida_entre_archivos(tmp_path):
    _escribir_horario(tmp_path, {"2020-01-02 12:00": 1.0}, nombre="a")
    _escribir_horario(tmp_path, {"2020-01-02 12:00": 9.0}, nombre="b")
    d, _ = _diario(tmp_path)
    assert d.loc["2020-01-02"] == 1.0                     # se conserva el primer archivo (orden alfabético)


# ---------- Hallazgo #2: correlación DGA–AGROMET (diagnóstico) ----------
def test_hallazgo2_correlacion():
    from hidro.io.imputacion import correlacion_con_agromet
    dias = pd.date_range("2020-01-01", periods=60)
    lluvia = np.where(np.arange(60) % 5 == 0, np.arange(60) % 17, 0.0)
    dga = pd.DataFrame({"FECHA_DT": dias, "Valor_Registrado": lluvia})
    agro = pd.DataFrame({"FECHA_DT": dias, "Precip_mm": 2 * lluvia + 1})
    r = correlacion_con_agromet(dga, agro)
    assert r.n_dias == 60 and r.r == pytest.approx(1.0)
    pocos = correlacion_con_agromet(dga.head(10), agro)
    assert pocos.n_dias == 10 and np.isnan(pocos.r)


def test_hallazgos_5_6_configurados():
    s = cargar_settings()
    assert (s.agromet_desfase_horas, s.agromet_horas_min_dia) == (8, 24)


def test_hallazgo7_factor_configurado():
    t = cargar_settings().tormenta
    assert (t.factor_intervalo_fijo, t.factor_min, t.factor_max) == (1.13, 1.0, 1.2)
