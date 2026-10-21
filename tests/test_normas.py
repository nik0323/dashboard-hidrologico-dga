"""Módulo de normas: evaluación con censura DGA, resumen y archivo config/normas.toml."""

import numpy as np
import pandas as pd
import pytest

from hidro.config import cargar_settings
from hidro.core.calidad import BAJO_LD, COL_CATEGORIA, CUANTIFICADO, SIN_MARCA, SOBRE_RANGO
from hidro.core.normas import (CUMPLE, CUMPLE_BAJO_LD, EXCEDE, INDETERMINADO, NO_EVALUABLE, SIN_DATOS,
                               SIN_PARAMETRO_DGA, UNIDAD_INCOMPATIBLE, Limite, evaluar_muestras,
                               normalizar_unidad, resumen_cumplimiento)
from hidro.io.normas import cargar_normas

# Parámetros presentes en calidad_agua_historico.txt (columna PARAMETRO, revisado 2026-10-21)
PARAMETROS_DGA = {
    "Aluminio Total", "Aluminio disuelto", "Arsenico total", "Bicarbonato", "Boro", "Cadmio total",
    "Calcio disuelto", "Calcio total", "Carbonato", "Cianuro", "Cloruro", "Cobalto Total", "Cobre disuelto",
    "Cobre total", "Coliformes Fecales", "Coliformes Totales", "Color", "Conductividad Especifica",
    "Cromo Hexavalente Disuelto", "Cromo Hexavalente Total", "Demanda Bioquimica de Oxigeno - 5 dias",
    "Demanda Quimica de Oxigeno", "Dureza (CaCO3)", "Fierro Disuelto", "Fierro total", "Fluoruro", "Fosfato",
    "Fosforo total", "HUMEDAD RELATIVA (PSICROMETRO)", "Litio disuelto", "Magnesio disuelto", "Magnesio total",
    "Manganeso disuelto", "Manganeso total", "Mercurio disuelto", "Mercurio total", "Molibdeno disuelto",
    "Niquel disuelto", "Niquel total", "Nitrato", "Nitrito", "Nitrogeno Amoniacal", "Nitrogeno Organico",
    "Nitrógeno Total", "Oxigeno Disuelto", "Ph", "Plata total", "Plomo disuelto", "Plomo total",
    "Potasio disuelto", "Potasio total", "Razon de Absorción de Sodio (RAS)", "Salinidad", "Selenio disuelto",
    "Selenio total", "Silice", "Sodio disuelto", "Sodio total", "Solidos Suspendidos Totales", "Sulfato",
    "Temperatura del Agua", "Transparencia", "Turbiedad Nefelometrica", "Zinc disuelto", "Zinc total",
}

MAXIMO = Limite(norma="n", parametro="Cadmio", parametros_dga=("Cadmio total",), unidad_dga="mg/l", maximo=0.01)
RANGO = Limite(norma="n", parametro="pH", parametros_dga=("Ph",), unidad_dga="unid.", minimo=6.5, maximo=8.5)


def _muestras(valores, marcas, parametro="Cadmio total", unidad="mg/l Cd"):
    return pd.DataFrame({
        "FECHA_DT": pd.date_range("2020-01-01", periods=len(valores), freq="MS"),
        "PARAMETRO": parametro, "UNIDAD": unidad, "Valor_Registrado": valores, COL_CATEGORIA: marcas,
    })


def test_evaluar_maximo_con_censura():
    df = _muestras([0.005, 0.02, 0.01, 0.001, 0.05, 0.02, 0.005, 0.03],
                   [CUANTIFICADO, CUANTIFICADO, SIN_MARCA, BAJO_LD, BAJO_LD, SOBRE_RANGO, SOBRE_RANGO, "Otra marca (D)"])
    assert evaluar_muestras(df, MAXIMO).tolist() == [
        CUMPLE, EXCEDE, CUMPLE,        # medidas: 0.01 = límite cumple
        CUMPLE_BAJO_LD,                # < 0.001 con LD bajo el límite
        INDETERMINADO,                 # < 0.05: LD sobre el límite, no se sabe
        EXCEDE,                        # > 0.02 >= 0.01
        INDETERMINADO,                 # > 0.005: puede o no superar 0.01
        NO_EVALUABLE,
    ]


def test_evaluar_rango_ph():
    df = _muestras([6.4, 7.0, 8.6, 6.0, 7.0, 9.0], [CUANTIFICADO] * 3 + [BAJO_LD, BAJO_LD, SOBRE_RANGO], "Ph", "unid. ph")
    assert evaluar_muestras(df, RANGO).tolist() == [EXCEDE, CUMPLE, EXCEDE, EXCEDE, INDETERMINADO, EXCEDE]


def test_resumen_estados_y_porcentaje():
    df = pd.concat([
        _muestras([0.005, 0.02, 0.001, 0.05], [CUANTIFICADO, CUANTIFICADO, BAJO_LD, BAJO_LD]),
        _muestras([7.0, 7.2], [CUANTIFICADO, CUANTIFICADO], "Ph", "mg/l"),          # unidad incorrecta
    ], ignore_index=True)
    limites = [MAXIMO, RANGO,
               Limite(norma="n", parametro="Bario", parametros_dga=(), unidad_dga="mg/l", maximo=4.0),
               Limite(norma="n", parametro="Boro", parametros_dga=("Boro",), unidad_dga="mg/l", maximo=0.75)]
    r = resumen_cumplimiento(df, "PARAMETRO", limites).set_index("Parámetro")
    cd = r.loc["Cadmio"]
    assert (cd["Muestras"], cd["Determinadas"], cd["Excedencias"], cd["Indeterminadas"]) == (4, 3, 1, 1)
    assert cd["% excedencia"] == pytest.approx(100 / 3)
    assert cd["Máx. medido"] == 0.02 and cd["Estado"] == EXCEDE
    assert r.loc["pH", "Estado"] == UNIDAD_INCOMPATIBLE
    assert r.loc["Bario", "Estado"] == SIN_PARAMETRO_DGA
    assert r.loc["Boro", "Estado"] == SIN_DATOS


def test_resumen_solo_indeterminadas():
    r = resumen_cumplimiento(_muestras([0.05, 0.05], [BAJO_LD, BAJO_LD]), "PARAMETRO", [MAXIMO])
    assert r.loc[0, "Estado"] == INDETERMINADO and np.isnan(r.loc[0, "% excedencia"])


@pytest.mark.parametrize("unidad, esperado", [("Mg/L Al", "mg/l"), ("unid. ph", "unid."), ("mg/l    ", "mg/l"),
                                              ("", ""), (None, "")])
def test_normalizar_unidad(unidad, esperado):
    assert normalizar_unidad(unidad) == esperado


def test_archivo_normas_valido_y_mapeado_a_parametros_dga():
    normas, limites = cargar_normas(cargar_settings().archivo_normas)
    assert set(normas) == {"nch409", "nch1333_riego"}
    for lim in limites:
        assert set(lim.parametros_dga) <= PARAMETROS_DGA, (lim.norma, lim.parametro)
    pares = [(lim.norma, lim.parametro) for lim in limites]
    assert len(pares) == len(set(pares)), "límite repetido"


def test_cargar_normas_rechaza_invalidos(tmp_path):
    ruta = tmp_path / "normas.toml"
    ruta.write_text(
        '[[norma]]\nclave = "a"\nnombre = "A"\n'
        '[[limite]]\nnorma = "x"\nparametro = "P1"\nunidad_dga = "mg/l"\nmaximo = 1.0\n'
        '[[limite]]\nnorma = "a"\nparametro = "P2"\nunidad_dga = "mg/l"\n'
        '[[limite]]\nnorma = "a"\nparametro = "P3"\nunidad_dga = "mg/l"\nminimo = 9.0\nmaximo = 1.0\n',
        encoding="utf-8")
    with pytest.raises(ValueError, match=r"norma desconocida(.|\n)*requiere maximo(.|\n)*minimo >= maximo"):
        cargar_normas(ruta)
