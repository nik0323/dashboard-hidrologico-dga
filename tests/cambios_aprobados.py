"""Registro de cambios numéricos aprobados respecto del dashboard original.

Cada entrada es un caso de `casos.py` cuya salida en `hidro` DEBE diferir del golden del
original. `test_regresion_hidro.py` exige que el conjunto de casos que difieren sea exactamente
este: un cambio no registrado, o una corrección que no tuvo efecto, hace fallar los tests.
"""

CAMBIOS_APROBADOS = {
    "imputar_con_agromet": (
        "Hallazgo #1: la imputación AGROMET ya no extiende la serie fuera del periodo DGA. "
        "Hallazgo #1b: no se imputan años con cobertura DGA < 80 %."),
    "precipitaciones_con_agromet": "Hallazgos #1, #1b, #4, #5 y #6: PMA, cuantiles y resumen de imputación.",
    "cargar_agromet": ("Hallazgo #5: día pluviométrico 08-08 h. Hallazgo #6: horas faltantes y rechazadas por QA "
                       "como faltantes (no 0) y solo días completos (24 h)."),
    "precipitaciones_sin_agromet": "Hallazgos #4 y #9: PMA sin años incompletos y tabla KS con bootstrap.",
    "caudales": "Hallazgo #4: QMA excluye años con cobertura < 80 %.",
    "ajustar_distribuciones": ("Hallazgo #9: tabla KS con D crítico exacto (kstwo), p-valor bootstrap "
                               "paramétrico y resultado según el bootstrap. Cuantiles sin cambio."),
    "dms_a_decimal": ("Hallazgo #13: |v| <= 180 siempre es grado decimal (-34.0 ya no es 0°0'34''), "
                      "0 = coordenada faltante (NaN)."),
}
