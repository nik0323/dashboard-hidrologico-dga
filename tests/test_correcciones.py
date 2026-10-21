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
