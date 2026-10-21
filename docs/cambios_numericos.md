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

**Sin cambio con esta corrección:** SAN FERNANDO, RIO CLARO EN EL VALLE, CONVENTO VIEJO, RIO
TINGUIRIRICA BAJO LOS BRIONES, MILLAHUE y LA RUFINA. Su registro DGA continúa hasta 2026, así que
2021-2023 quedan *dentro* del periodo. Sin embargo, el archivo DGA no trae datos de esos tres años
(salvo en CONVENTO VIEJO), por lo que AGROMET los seguía rellenando completos. Eso se resuelve en
el hallazgo #1b.

## Hallazgo #1b: la imputación AGROMET completaba años sin registro DGA

**Problema.** Dentro del periodo de registro, la imputación rellenaba cualquier día faltante.
En el archivo `prep_diarias_historico_6.txt` faltan completos los años 2021, 2022 y 2023 en casi
todas las estaciones. Por eso AGROMET (Placilla Chacarilla) aportaba 1.094 días, es decir, tres
PMA anuales enteras tomadas de otra estación.

**Corrección.** Solo se rellenan vacíos en años calendario con cobertura DGA >= 80 %. La cobertura
es el número de días distintos con registro dividido por 365 o 366
(`[imputacion].cobertura_min_anual` en `config/settings.toml`; umbral aprobado por el usuario).
Los años bajo el umbral conservan solo sus días DGA y la app los lista en el panel de imputación.
El comportamiento original queda disponible con la casilla "Imputación sin restricciones
(dashboard original)", que en código corresponde a `extender=True, cobertura_min_anual=0`.

**Efecto sobre los datos reales** (mismas estaciones y fuentes que en el hallazgo #1; "Corregido"
incluye las correcciones #1 y #1b):

| Estación | Variante | n años | P24 T=100 mejor [mm] | P24 T=100 Gumbel [mm] | Días imputados |
|---|---|---|---|---|---|
| SAN FERNANDO | Solo DGA | 53 | 171.68 (LP-III) | 178.96 | 0 |
| | Original | 56 | 173.46 (LP-III) | 177.46 | 1.094 |
| | **Corregido** | **53** | **171.68** (LP-III) | **178.96** | **0** |
| RIO CLARO EN EL VALLE | Solo DGA | 8 | 73.08 (LP-III) | 90.45 | 0 |
| | Original | 11 | 96.01 (LP-III) | 101.17 | 1.094 |
| | **Corregido** | **8** | **73.08** (LP-III) | **90.45** | **0** |
| RIO TINGUIRIRICA BAJO LOS BRIONES | Solo DGA | 25 | 126.85 (Log-Normal) | 129.50 | 0 |
| | Original | 28 | 139.89 (LP-III) | 128.36 | 1.094 |
| | **Corregido** | **25** | **126.85** (Log-Normal) | **129.50** | **0** |
| MILLAHUE | Solo DGA | 52 | 133.36 (LP-III) | 162.65 | 0 |
| | Original | 55 | 136.64 (LP-III) | 161.96 | 1.094 |
| | **Corregido** | **52** | **133.36** (LP-III) | **162.65** | **0** |
| LA RUFINA | Solo DGA | 64 | 169.92 (LP-III) | 193.56 | 0 |
| | Original | 67 | 172.05 (LP-III) | 194.47 | 1.094 |
| | **Corregido** | **64** | **169.92** (LP-III) | **193.56** | **0** |
| CONVENTO VIEJO | todas | 56 | 117.19 (LP-III) | 132.30 | 15 en "Original" y "Corregido" (vacíos cortos) |

**Conclusión.** Con los datos actuales, en las 10 estaciones a <= 30 km, la serie corregida da
los mismos cuantiles que la serie solo DGA. La única imputación que sobrevive son 15 días
aislados en CONVENTO VIEJO, que no alteran ninguna PMA. Los cuantiles reportados antes con
AGROMET activado (opción por defecto del dashboard original) estaban influidos por 3 años de
lluvia de Placilla Chacarilla en 7 de las 10 estaciones; en RIO CLARO EN EL VALLE la diferencia
es de +31 % en P24 T=100.

## Hallazgo #4: años incompletos en la serie de máximos anuales (PMA y QMA)

**Problema.** El máximo anual se calculaba con todos los años presentes, sin revisar cuántos días
con registro tenían. Un año parcial puede no incluir el evento máximo. Por ejemplo, 2026 trae datos
solo hasta el 31/05, antes del peak invernal. Esos años entraban con una PMA o QMA subestimada.

**Corrección.** Solo entran a la serie de máximos los años calendario con cobertura >= 80 %
(días distintos con registro / 365 o 366; `[maximos_anuales].cobertura_min_anual` en
`config/settings.toml`; umbral aprobado por el usuario). Se aplica a la PMA (precipitaciones) y
al QMA (caudales), y la app muestra los años excluidos. Con `cobertura_min_anual = 0` se
reproduce el dashboard original. [SUPUESTO: año calendario; no se evaluó la cobertura de la
temporada húmeda por separado.]

**Efecto sobre la PMA (datos reales, estaciones a <= 30 km).** "Original" corresponde al dashboard
inicial con AGROMET activado por defecto. "Final" incluye las correcciones #1, #1b y #4.

| Estación | Excluidos por #4 | n (original → final) | P24 T=100 mejor [mm], original → final | P24 T=100 Gumbel [mm], original → final |
|---|---|---|---|---|
| SAN FERNANDO | 1971, 2026 | 56 → 51 | 173.46 → **170.01** (LP-III) | 177.46 → **180.19** |
| RIO CLARO EN EL VALLE | 2016, 2020, 2026 | 11 → 5 | 96.01 → **70.07** (LP-III) | 101.17 → **92.33** |
| CONVENTO VIEJO | 1971, 2026 | 56 → 54 | 117.19 → **115.23** (LP-III) | 132.30 → **132.76** |
| RIO TINGUIRIRICA BAJO LOS BRIONES | 2002, 2026 | 28 → 23 | 139.89 (LP-III) → **131.84** (Gumbel) | 128.36 → **131.84** |
| VIÑA VIEJA | 2003 | 41 → 37 | 127.52 → **127.88** (LP-III) | 147.82 → **150.59** |
| MILLAHUE | 1976, 2006, 2026 | 55 → 49 | 136.64 → **156.41** (LP-III) | 161.96 → **158.30** |
| LA RUFINA | 2026 | 67 → 63 | 172.05 → **168.00** (LP-III) | 194.47 → **193.48** |
| PANIAHUE | 1988 | 13 → 9 | 183.28 → **180.82** (LP-III) | 171.52 → **176.16** |
| TRANQUE LAS PATAGUAS | 2025 | 4 → 0 | 134.38 → sin ajuste | 144.94 → sin ajuste |
| TRANQUE MILLAHUE | 2025 | 4 → 0 | 147.55 → sin ajuste | 133.28 → sin ajuste |

Observaciones:
- En MILLAHUE, al excluir 3 años, LP-III a T=100 sube un 14,5 % respecto del original (y un
  17 % respecto de la serie solo DGA), mientras que Gumbel cambia menos de un 3 %. La asimetría
  muestral de log10 es sensible a pocos datos (hallazgo #10). Conviene justificar en el informe la
  distribución adoptada y no basarse solo en el menor D de la prueba KS.
- RIO CLARO EN EL VALLE queda con 5 años completos. La app ya advierte que con menos de 15 años
  la extrapolación a T altos tiene validez limitada.

**Efecto sobre el QMA (estaciones fluviométricas a <= 40 km).** Se excluyen entre 1 y 15 años por
estación. Casos notables: RIO TINGUIRIRICA EN PUENTE RUTA 90 (la estación que la app selecciona por
defecto) pasa de 3 a 0 años y la app lo informa; CANAL TENO EN KM. 13.465 pasa de 25 a 10; RIO
CLARO EN TUNCA, de 31 a 19. El QMA solo se grafica (no se ajustan distribuciones), así que este
cambio no afecta cuantiles reportados.
