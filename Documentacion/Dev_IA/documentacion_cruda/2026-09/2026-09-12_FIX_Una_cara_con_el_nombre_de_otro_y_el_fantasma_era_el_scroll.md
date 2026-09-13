# Una cara con el nombre de otro, y el fantasma era el scroll

**2026-09-12** · commits `5525833` (audit de latencia), `2723591` (fix de la librería), `23b4323`
(cierre del censo). Migraciones `_30` y `_31`.

Tres armas no se podían atribuir y el censo de rangos S y A no cerraba. Las tres causas estaban en
los **datos** —la librería de avatares y el inventario—, no en el código, y las tres las destapó
instrumentación que se había agregado antes sin arreglar nada.

## 1 · El diagnóstico que se escribió tres veces

`Réplica de motor estelar` (Billy), `Transmorfer original` (Zhao) y `Tránsito herciano` (Billy
Estelar) salían como *"con dueño (sin identificar)"* o con el dueño **equivocado**. El sistema veía
la cara y se abstenía, que es lo correcto: el mínimo de margen (0.04) es lo único que impidió
escribir el arma de Billy a nombre de Ben.

| PJ | antes | después | qué era |
|---|---|---|---|
| Billy | top `Ben 0.422`, margen 0.027 | `Billy` **0.172**, margen 0.250 | le faltaba su cara |
| Zhao | top `Zhao 0.306`, margen 0.029 | `Zhao` **0.120**, margen 0.215 | refs con el encuadre viejo |
| Billy Estelar | `Billy` 0.16 vs `Estelar` 0.26 | `Billy Estelar` **0.156**, margen 0.272 | **su cara etiquetada como Billy** |

**El umbral no se tocó.** Era la tentación obvia para Zhao —"le falta un poquito de margen"— y
habría sido el arreglo equivocado: el mismo umbral estaba impidiendo un error real en otro PJ.

### Billy y Zhao: cosecha guiada

El único camino que aprende una cara con etiqueta certera es la ficha del PJ con el botón
*Desequipar*: ahí el juego AFIRMA el dueño y no hace falta la librería
(`_maybe_harvest_weapon_owner`). Daniel pasó por las dos fichas y la librería creció de 103 a 105
refs. Nada de código.

### Billy Estelar: una ref con el nombre de otro

`Billy Estelar` **no es un atuendo**: en `agents` es otro PJ (id 47, rango S, Disruptivos) frente a
Billy (id 12, A, Ataque), con sus propios discos y su propia arma. La clase `Billy` tenía **una
ref vieja que era la cara de Estelar**, y como la distancia de una clase es la de su **mejor** ref,
Billy le ganaba a Estelar en el arma de Estelar. Medido ref por ref contra ese badge: la intrusa
daba **0.156** y la de Billy **0.475**.

Se **movió** la ref a su clase; no se borró (B3), con backup del `.npz`.

## 2 · Tres lecciones, y dos son errores míos

**⭐ Medir con la métrica del sistema, no con una parecida.** Descarté la hipótesis correcta
comparando las refs con una distancia L2 sobre la imagen en gris en vez de `descriptor_distance`.
Dio lejos, escribí "la hipótesis no se sostiene" y busqué en otro lado. Una medición con la
métrica equivocada no es media medición: **es una refutación falsa con aire de rigor**, y cierra la
puerta que había que abrir. Quedó en A1 de las prácticas.

**El veto de cosecha es el mejor detector de clases envenenadas.** Al intentar aprender desde la
ficha de Estelar, el juego decía "Billy Estelar" y el matcher afirmaba "Billy" ⇒ `veto_conflicto`,
sin aprender nada. La guarda existe para no envenenar una clase, y de paso **señala** las que ya lo
están: si el matcher contradice al juego, alguien tiene material ajeno.

**La instrumentación se paga sola.** El 2026-09-11 se agregó la posición de la selección al log
(`· @(x,y)`) sin arreglar nada — sólo para poder diagnosticar. Al día siguiente resolvió dos casos
(ver abajo). Vale como argumento la próxima vez que instrumentar parezca un rodeo.

## 3 · El fantasma de las copias era el SCROLL

En la última pasada entró una segunda `Transmorfer original` libre y Daniel tiene una sola. Con la
posición ya en el log:

    02:54:04  Transmorfer original · Nv 0/10 · P1 · LIBRE · @(402,1064)  → reusa la fila 55
    02:56:31  Transmorfer original · Nv 0/10 · P1 · LIBRE · @(1484,680)  → inserta la fila 57

Las filas de la grilla caen en y ≈ 367, 600, 831 y 1064. **680 no es el centro de ninguna**: la
grilla estaba scrolleada, el mismo tile apareció en otro lugar y el ordinal de copia —que sólo sabe
de posiciones— lo leyó como otra pieza. Era el límite que el reporte del censo ya declaraba; ahora
está probado, y explica también la fila 50 del Rotor (mig `_29`), corregida a ciegas el día
anterior.

Las dos filas quedaron con `descartado = 1` (baja lógica, reversible). **Sigue abierto** que el
ordinal distinga un scroll de una copia nueva; hoy se corrige a mano cuando aparece.

## 4 · La latencia, medida y sin tocar nada

1587 muestras con `-Metrics`. Detalle completo en `audit/latencia_y_badges_20260912.md`.

| superficie | p50 | presupuesto |
|---|---|---|
| `capturer` | 46 ms | 50 |
| `detector` (classify) | 191 ms | 50 |
| `dispatch:S30` (el ciclo del inventario) | **1569 ms** | 1500 (su cadencia) |
| `dispatch:S26` | 2679 ms | 1000 |

**La sospecha previa era el OCR del título** que `classify` hace en cada ciclo para distinguir el
inventario de armas del de discos. Es real (191 ms, 4× su presupuesto) pero es **un octavo** del
ciclo: no es la causa.

Medidas offline, las etapas del handler suman **~480 ms** (parseo del panel 468, badge ~0, firma 1,
localización 12). Entre eso y los 1569 ms de la app **faltan ~1,1 s sin explicación**. La diferencia
entre las dos mediciones es que la app manda el OCR a otro proceso, así que el sospechoso es el ida
y vuelta con el worker — **y eso es una hipótesis, no un hallazgo**.

**Lo que sigue, en este orden:** partir `dispatch:S30` en sub-bloques con `metrics.measure_block`
(instrumentar, no optimizar), y recién con esos números decidir. Dos hallazgos sueltos: `ocr_text`
tiene un máximo de **12,5 s** que coincide con el relevo del worker por techo de memoria, y
`frescura_estado_a_log` guarda un timestamp como si fuera una duración — **la métrica está rota**.

## 5 · Estado al cerrar

- **El censo de rangos S y A cerró: `inventory_weapons` = 56 filas activas** (46 equipadas + 10
  libres), exactamente el contador del header con el filtro S+A. La última en entrar fue la Réplica
  de Billy, que pudo escribirse recién cuando la mig `_30` sacó el conflicto.
- Los 5 PJs sin arma (Anby, Harumasa, Lucy, Nekomata, Soukaku) **no tienen ninguna equipada**,
  confirmado por Daniel. Rango B sigue fuera de alcance.
- Tests: 35 de verdad de tierra en verde y **ningún `xfail`**; miden contra el snapshot nuevo
  `audit/avatar_detbadge_v2_snapshot_20260912_billy_estelar.npz`. Si alguien vuelve al snapshot
  viejo, los tres tests se ponen rojos por la razón correcta.

## Queda abierto

1. **Latencia**: instrumentar el ciclo por dentro; los ~1,1 s sin explicar.
2. **`frescura_estado_a_log`**: métrica rota.
3. **El ordinal de copias no distingue scroll**.
4. **La interfaz** — Daniel la planteó el 2026-09-12: *"seguimos con la misma interfaz desde el
   comienzo"*. Se ve en la próxima sesión. Hay material previo: el brief y los mockups de
   `Documentacion/Interfaz/`, y la deuda ya anotada de los toasts (íconos y tipografía chicos).
