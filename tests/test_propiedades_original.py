"""Propiedades físicas/matemáticas que el original debe cumplir, independientes del golden."""

import numpy as np
import pandas as pd
import pytest

from casos import SERIES_PMA, api_original


@pytest.fixture(scope="module")
def api():
    return api_original()


@pytest.mark.parametrize("dt", [5, 10, 15, 30])
@pytest.mark.parametrize("b", [0.1, 0.33, 0.5])
def test_hietograma_conserva_p24(api, dt, b):
    tiempos, hieto = api.hietograma_bloques_alternos(87.3, dt, 24, b)
    assert len(hieto) == 24 * 60 // dt
    assert tiempos[-1] == 24 * 60
    assert hieto.sum() == pytest.approx(87.3, abs=1e-9)
    assert hieto.argmax() == (len(hieto) - 1) // 2  # bloque mayor al centro


def test_haversine_referencias(api):
    assert api.haversine_vectorizado(-34.636, -71.024, -34.636, -71.024) == pytest.approx(0.0)
    # 1° de latitud ≈ 111.19 km con R = 6371 km
    assert api.haversine_vectorizado(-34.0, -71.0, -35.0, -71.0) == pytest.approx(111.195, abs=1e-3)


def test_dms_conocidos(api):
    assert api.dms_a_decimal(343810) == pytest.approx(-(34 + 38 / 60 + 10 / 3600))
    assert api.dms_a_decimal("0701819  ") == pytest.approx(-(70 + 18 / 60 + 19 / 3600))
    assert np.isnan(api.dms_a_decimal(346099))


def test_cuantiles_crecientes_con_t(api):
    aj = api.ajustar_distribuciones(SERIES_PMA["gumbel_30"](np.random.default_rng(2)))
    for dist, q in aj["cuantiles"].items():
        assert np.all(np.diff(list(q.values())) > 0), dist


def test_gumbel_momentos_formula_cerrada(api):
    """x_T = u - α·ln(-ln(1 - 1/T)), con α = σ√6/π y u = μ - 0.5772α."""
    x = SERIES_PMA["gumbel_30"](np.random.default_rng(2))
    alpha = np.std(x, ddof=1) * np.sqrt(6) / np.pi
    u = np.mean(x) - 0.5772 * alpha
    aj = api.ajustar_distribuciones(x)
    for t, v in aj["cuantiles"]["Gumbel"].items():
        assert v == pytest.approx(u - alpha * np.log(-np.log(1 - 1 / t)), abs=1e-9)


def test_cn_scs(api):
    r = api.cn_retencion(pd.DataFrame({"CN_Teórico": [80], "%_Área": [100.0]}))
    assert r["s_ret"] == pytest.approx(25400 / 80 - 254)
    assert r["ia"] == pytest.approx(0.2 * r["s_ret"])


def test_kirpich_valor_manual(api):
    r = api.tc_cuenca(15.5, 8.2, "Pendiente Media (m/m)", 0.045)
    assert r["tc_kirpich"] == pytest.approx(0.0663 * 8.2 ** 0.77 / 0.045 ** 0.385, abs=1e-12)
