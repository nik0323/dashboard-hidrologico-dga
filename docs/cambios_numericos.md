# Cambios numéricos respecto del dashboard original

Cada cambio fue aprobado de forma explícita, se implementó en un commit propio y quedó registrado
en `tests/cambios_aprobados.py`. Los resultados de "antes" se reproducen con la opción indicada.

## Hallazgo #1: la imputación AGROMET extendía la serie fuera del periodo DGA

**Problema.** `imputar_con_agromet` alineaba la serie DGA y la AGROMET usando la *unión* de sus
fechas. Si una estación DGA terminó antes (o empezó después) que AGROMET (2021-2023), los años
fuera de su registro se agregaban completos con lluvia de Placilla Chacarilla. Así entraban a la
serie de PMA y modificaban n, los momentos, los cuantiles y la prueba KS.

**Corrección.** Por defecto, `imputar_con_agromet(df_dga, df_agro)` solo rellena días entre la
primera y la última fecha con registro DGA. El comportamiento anterior queda disponible con
`extender=True` (en la app: casilla "Extender serie fuera del periodo DGA", desactivada por
defecto y con advertencia visible).

**Efecto sobre los datos reales.** Estaciones a <= 30 km de Lo Moscoso, `prep_diarias_historico_6.txt`
y AGROMET Placilla Chacarilla del 01/01/2021 al 31/12/2023. "Mejor" es la distribución con menor D de KS.

| Estación | Registro DGA | Variante | n años | P24 T=100 mejor [mm] | P24 T=100 Gumbel [mm] |
|---|---|---|---|---|---|
| VIÑA VIEJA | 1960 – jul 2003 | Solo DGA | 38 | 126.09 (LP-III) | 149.37 |
| | | Antes (extiende) | 41 | 127.52 (LP-III) | 147.82 |
| | | **Corregido** | **38** | **126.09** (LP-III) | **149.37** |
| PANIAHUE | 1979 – ago 1988 | Solo DGA | 10 | 178.37 (LP-III) | 179.19 |
| | | Antes (extiende) | 13 | 183.28 (LP-III) | 171.52 |
| | | **Corregido** | **10** | **178.37** (LP-III) | **179.19** |
| TRANQUE LAS PATAGUAS | ene – sep 2025 | Solo DGA | 1 | sin ajuste | sin ajuste |
| | | Antes (extiende) | 4 | 134.38 (LP-III) | 144.94 |
| | | **Corregido** | **1** | **sin ajuste** | **sin ajuste** |
| TRANQUE MILLAHUE | ene – abr 2025 | Solo DGA | 1 | sin ajuste | sin ajuste |
| | | Antes (extiende) | 4 | 147.55 (LP-III) | 133.28 |
| | | **Corregido** | **1** | **sin ajuste** | **sin ajuste** |

Antes, en las dos estaciones "Tranque" se reportaban cuantiles de diseño a T = 100 años
construidos con 3 años de AGROMET y 1 año parcial de DGA.

**Sin cambio:** SAN FERNANDO, RIO CLARO EN EL VALLE, CONVENTO VIEJO, RIO TINGUIRIRICA BAJO LOS
BRIONES, MILLAHUE y LA RUFINA. Su registro DGA continúa hasta 2026, así que 2021-2023 quedan
*dentro* del periodo. Sin embargo, el archivo DGA no trae datos de esos tres años (salvo en
CONVENTO VIEJO), por lo que AGROMET los rellena completos (1.094 días). Este es un problema
distinto, que sigue abierto: rellenar años completos dentro del periodo con otra estación. Por
ejemplo, en RIO CLARO EN EL VALLE, P24 T=100 pasa de 73.08 mm (8 años DGA) a 96.01 mm (11 años,
3 de ellos AGROMET).
