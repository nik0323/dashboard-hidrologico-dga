"""La caché de lectura se invalida cuando el archivo cambia en disco (hallazgo #18)."""

import os

from casos import csv_caudales
from hidro.ui import cache


def test_cache_detecta_archivo_modificado(tmp_path):
    ruta = tmp_path / "caudal.txt"
    ruta.write_bytes(csv_caudales())
    n1 = len(cache.cargar_serie_dga(str(ruta), "CAUDAL"))

    lineas = csv_caudales().decode("utf-8").splitlines()
    ruta.write_text("\n".join(lineas[:101]) + "\n", encoding="utf-8")
    os.utime(ruta, (1, 1))  # fuerza mtime distinto aunque el sistema de archivos tenga baja resolución

    assert n1 > 100
    assert len(cache.cargar_serie_dga(str(ruta), "CAUDAL")) == 100
