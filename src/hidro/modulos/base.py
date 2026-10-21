"""Contrato común de los módulos de análisis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from hidro.contexto import Contexto


class Modulo(ABC):
    """Un módulo de análisis de la barra lateral.

    clave: identificador único (prefijo de keys de widgets); nombre: texto en el menú;
    orden: posición en el menú; archivos_requeridos: claves de [datos.archivos] que usa
    (vacío si trabaja solo con entradas manuales).
    """

    clave: ClassVar[str]
    nombre: ClassVar[str]
    orden: ClassVar[int] = 100
    archivos_requeridos: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def render(self, ctx: Contexto) -> None:
        """Dibuja el módulo completo en la página."""
