"""settings.toml reproduce las constantes del original y se valida al cargar."""

from pathlib import Path

import numpy as np
import pytest

from casos import api_original
from hidro.config import RAIZ_PROYECTO, RUTA_SETTINGS_DEFECTO, cargar_settings


@pytest.fixture(autouse=True)
def sin_variables_entorno(monkeypatch):
    monkeypatch.delenv("DGA_DATA_DIR", raising=False)
    monkeypatch.delenv("HIDRO_SETTINGS", raising=False)


def test_settings_igual_a_constantes_originales():
    o = api_original()
    s = cargar_settings()
    assert s.archivos == o.ARCHIVOS
    assert s.patron_agromet == o.PATRON_AGROMET
    assert (s.punto_control.nombre, s.punto_control.lat, s.punto_control.lon) == (o.NOMBRE_REF, o.LAT_REF, o.LON_REF)
    np.testing.assert_array_equal(np.asarray(s.t_objetivo), o.T_OBJETIVO)
    assert np.asarray(s.t_objetivo).dtype == o.T_OBJETIVO.dtype
    assert (s.n_min_ajuste, s.n_recomendado) == (o.N_MIN_AJUSTE, o.N_RECOMENDADO)
    assert s.qa_max_precip_horaria_mm == o.QA_MAX_PRECIP_HORARIA
    # Radios de los sliders en modulo_* (dashboard_dga.py:376, 434, 720, 772, 817)
    originales = ("precipitaciones", "caudales", "pozos", "calidad")
    assert {k: (r.defecto, r.max, r.paso, r.min) for k, r in s.radios.items() if k in originales} == {
        "precipitaciones": (30, 100, 5, 10), "caudales": (40, 100, 5, 10),
        "pozos": (50, 100, 5, 10), "calidad": (60, 200, 10, 10),
    }
    assert s.radio("normas") == s.radio("calidad")   # módulo nuevo: mismo radio que calidad
    # Selectores de la tormenta de diseño (dashboard_dga.py:559-561)
    assert s.tormenta.t_diseno == (50, 100, 500)
    assert s.tormenta.dt_minutos == (5, 10, 15, 30)
    assert (s.tormenta.b_defecto, s.tormenta.b_min, s.tormenta.b_max) == (0.33, 0.1, 0.5)


def test_directorio_relativo_y_variable_de_entorno(monkeypatch, tmp_path):
    assert cargar_settings().directorio_datos == RAIZ_PROYECTO
    monkeypatch.setenv("DGA_DATA_DIR", str(tmp_path))
    assert cargar_settings().directorio_datos == tmp_path


def test_settings_invalido(tmp_path):
    texto = RUTA_SETTINGS_DEFECTO.read_text(encoding="utf-8")
    malo = tmp_path / "config" / "settings.toml"
    malo.parent.mkdir()
    malo.write_text(texto.replace("t_diseno = [50, 100, 500]", "t_diseno = [50, 100, 1000]")
                        .replace("defecto = 30", "defecto = 5"), encoding="utf-8")
    with pytest.raises(ValueError, match=r"t_diseno(.|\n)*radios.precipitaciones"):
        cargar_settings(malo)
