"""Clasificación de mediciones de pozos según la columna OBSERVACION de la DGA (hallazgo #12)."""

from __future__ import annotations

import pandas as pd

from hidro.core import columnas as c

COL_OBSERVACION = "OBSERVACION"
COL_CONDICION = "Condición"

ESTATICO = "Estático"
SURGENTE = "Surgente"
DINAMICO = "Dinámico"
SECO = "Seco"
SIN_ACCESO = "Sin acceso"
EMBANCADO = "Embancado"
OBSERVACIONES_DGA = {"": ESTATICO, "surgente": SURGENTE, "dinamico": DINAMICO, "dinámico": DINAMICO,
                     "seco": SECO, "sin acceso": SIN_ACCESO, "embancado": EMBANCADO}

# Condiciones cuyo valor representa un nivel estático: sin observación y surgente (nivel sobre
# la superficie, profundidad negativa). Dinámico (con bombeo) y Embancado (pozo obstruido) no.
CONDICIONES_NIVEL_ESTATICO = (ESTATICO, SURGENTE)


def clasificar_condicion(df: pd.DataFrame) -> pd.Series:
    """Condición de cada medición según OBSERVACION; vacía = Estático; otros textos = "Otra (x)"."""
    if COL_OBSERVACION not in df.columns:
        return pd.Series(ESTATICO, index=df.index, name=COL_CONDICION)
    obs = df[COL_OBSERVACION].fillna("").astype(str).str.strip()
    return obs.map(lambda o: OBSERVACIONES_DGA.get(o.lower(), f"Otra ({o})")).rename(COL_CONDICION)


def niveles_estaticos(df: pd.DataFrame) -> pd.DataFrame:
    """Mediciones con nivel estático válido [m bajo la superficie; negativo = surgente]."""
    cond = df[COL_CONDICION] if COL_CONDICION in df.columns else clasificar_condicion(df)
    return df[cond.isin(CONDICIONES_NIVEL_ESTATICO) & df[c.VALOR].notna()]


def resumen_condiciones(df: pd.DataFrame) -> pd.DataFrame:
    """Mediciones por condición, cuántas tienen valor de nivel y si se usan como nivel estático."""
    cond = df[COL_CONDICION] if COL_CONDICION in df.columns else clasificar_condicion(df)
    tabla = (pd.DataFrame({COL_CONDICION: cond, "con_valor": df[c.VALOR].notna()})
             .groupby(COL_CONDICION).agg(Mediciones=("con_valor", "size"), **{"Con nivel": ("con_valor", "sum")})
             .reset_index().sort_values("Mediciones", ascending=False, ignore_index=True))
    tabla["Usada como nivel estático"] = tabla[COL_CONDICION].isin(CONDICIONES_NIVEL_ESTATICO)
    return tabla
