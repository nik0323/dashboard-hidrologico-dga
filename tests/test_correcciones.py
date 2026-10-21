"""Propiedades de las correcciones aprobadas (ver cambios_aprobados.py)."""

import numpy as np
import pandas as pd
import pytest

from casos import RUTA_GOLDEN, _agromet, _serie_precip, api_original, comparar
from hidro.io.imputacion import imputar_con_agromet


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


def test_hallazgo1_extender_reproduce_original(entradas):
    golden = pd.read_pickle(RUTA_GOLDEN)["imputar_con_agromet"]
    for nombre, (dga, agro) in entradas.items():
        comparar(imputar_con_agromet(dga, agro, extender=True), golden[nombre], nombre)


def test_hallazgo1_solo_rellena_vacios_internos(entradas):
    for dga, agro in entradas.values():
        out = imputar_con_agromet(dga, agro)
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
    out = imputar_con_agromet(*entradas["sintetico"])
    # DGA: 01/01 (media 3), 03/01, 06/01; AGROMET rellena 02, 04 y 05/01 con 3, 5 y 6 mm
    assert out["FECHA_DT"].dt.strftime("%d/%m").tolist() == ["01/01", "02/01", "03/01", "04/01", "05/01", "06/01"]
    assert out["Valor_Registrado"].tolist() == [3.0, 3.0, 0.0, 5.0, 6.0, 10.0]
    assert out["IMPUTADO"].tolist() == [False, True, False, True, True, False]
