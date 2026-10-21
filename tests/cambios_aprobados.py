"""Registro de cambios numéricos aprobados respecto del dashboard original.

Cada entrada es un caso de `casos.py` cuya salida en `hidro` DEBE diferir del golden del
original. `test_regresion_hidro.py` exige que el conjunto de casos que difieren sea exactamente
este: un cambio no registrado, o una corrección que no tuvo efecto, hace fallar los tests.
"""

CAMBIOS_APROBADOS = {
    "imputar_con_agromet": "Hallazgo #1: la imputación AGROMET ya no extiende la serie fuera del periodo DGA.",
    "precipitaciones_con_agromet": "Hallazgo #1: PMA, cuantiles y resumen de imputación sin días fuera del periodo DGA.",
}
