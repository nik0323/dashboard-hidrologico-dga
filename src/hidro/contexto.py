"""Contexto de ejecución que la app entrega a cada módulo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hidro.config import Settings


@dataclass(frozen=True)
class Contexto:
    """settings: configuración cargada; dir_datos: carpeta de datos elegida en la barra lateral;
    clave_modulo: prefijo único para las keys de los widgets del módulo activo."""

    settings: Settings
    dir_datos: Path
    clave_modulo: str

    def key(self, nombre: str) -> str:
        """Key de widget con prefijo del módulo (evita colisiones y conserva estado por módulo)."""
        return f"{self.clave_modulo}__{nombre}"
