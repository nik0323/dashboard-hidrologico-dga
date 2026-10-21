"""Lectura y validación de config/normas.toml."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hidro.core.normas import Limite, Norma

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def cargar_normas(ruta: str | os.PathLike) -> tuple[dict[str, Norma], list[Limite]]:
    """Normas por clave y lista de límites. Lanza ValueError con todos los problemas encontrados."""
    with open(Path(ruta), "rb") as fh:
        crudo = tomllib.load(fh)

    normas: dict[str, Norma] = {}
    errores = []
    for n in crudo.get("norma", []):
        if n["clave"] in normas:
            errores.append(f"norma repetida: {n['clave']}")
        normas[n["clave"]] = Norma(clave=n["clave"], nombre=n["nombre"], fuente=n.get("fuente", ""))

    limites = []
    for i, l in enumerate(crudo.get("limite", []), start=1):
        etiqueta = f"limite #{i} ({l.get('norma')} / {l.get('parametro')})"
        lim = Limite(
            norma=l["norma"], parametro=l["parametro"], parametros_dga=tuple(l.get("parametros_dga", [])),
            unidad_dga=str(l.get("unidad_dga", "")).strip().lower(),
            maximo=float(l["maximo"]) if "maximo" in l else None,
            minimo=float(l["minimo"]) if "minimo" in l else None,
            verificado=bool(l.get("verificado", False)), nota=l.get("nota", ""),
        )
        if lim.norma not in normas:
            errores.append(f"{etiqueta}: norma desconocida")
        if lim.maximo is None and lim.minimo is None:
            errores.append(f"{etiqueta}: requiere maximo y/o minimo")
        if lim.maximo is not None and lim.minimo is not None and lim.minimo >= lim.maximo:
            errores.append(f"{etiqueta}: minimo >= maximo")
        if not lim.unidad_dga:
            errores.append(f"{etiqueta}: falta unidad_dga")
        limites.append(lim)

    if errores:
        raise ValueError(f"{ruta} inválido:\n- " + "\n- ".join(errores))
    return normas, limites
