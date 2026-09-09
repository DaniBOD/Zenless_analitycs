# Hoja de ruta del uso diario (acordada 2026-09-05)

> Daniel empezó a usar el sistema a diario para su farmeo. Este es el orden que pidió, con lo que
> cada tramo requiere y lo que se encontró al empezar el primero.

## Contexto operativo que cambia las prioridades

- **El farmeo es por pilas: ~5 corridas por día como máximo.** El volumen de discos nuevos es
  bajo, así que el costo por disco no es el problema; la **consistencia** sí.
- La app se abre y se cierra a mano (el watcher está escrito pero **no instalado**).
- Inventario real declarado por Daniel: **~400 discos**; la DB tiene 384.

---

## 1. Cada disco farmeado entra a la DB ✅ CERRADO 2026-09-06

Los **tres verbos** implementados. Detalle en
[`2026-09-06_FEAT_Los_tres_verbos_la_DB_sigue_al_juego_sola.md`](2026-09-06_FEAT_Los_tres_verbos_la_DB_sigue_al_juego_sola.md).

| verbo | trigger | estado |
|---|---|---|
| INSERT — el drop entra | `s3_drop_insert` | ✅ validado en vivo (6 drops → 6 filas) |
| baja — el desmontaje libera | `descartado=1` | ✅ validado en vivo (6 bajas, 384 exacto) |
| UPDATE — la mejora sigue al libre | `s10_upgrade_update` | ✅ validado en vivo (3 de 4; el 4º se abstuvo por OCR) |

Las dos fugas que este tramo tenía que resolver quedaron cerradas: **subir de nivel cambiaba la
identidad** (⇒ segunda fila) y **desmontar no borraba** (⇒ fila fantasma). La decisión que estaba
pendiente de Daniel —reconciliar con censos periódicos vs. cerrar el ciclo de vida— la resolvió
él: *"Los tres verbos completos"*.

### Lo que no se puede recuperar

Los drops del 2026-09-05 **no se pueden migrar retroactivamente**: el log guarda set/slot/main/
nivel pero **no los substats**, y sin ellos no hay identidad. Entran cuando Daniel recorra el
inventario.

## 2. Censo de armas / W-Engines 🟡 PRIMERA PASADA HECHA — 28 filas, falta cerrar la brecha

Detalle en
[`2026-09-06_FEAT_Censo_de_W_Engines_el_inventario_de_armas_existe.md`](2026-09-06_FEAT_Censo_de_W_Engines_el_inventario_de_armas_existe.md).

`inventory_weapons` existía desde la Fase 1 con **0 filas y sin un solo repo ni syncer**. La
captura ya estaba lista y medida (`parse_weapon_s30`: 60/60 campos sobre las 10 capturas reales);
faltaba toda la escritura. Ahora están la migración `_26`, los repos, el `WeaponSyncer`, el
contador del header compartido con discos, el censo (`InventoryCensus`) y el reporte de cierre.

**Regla de v1: se escribe lo que se NOMBRA, nunca lo que se declara libre.** Sale de una medición
—los 6 que el badge nombra salen los 6 bien, y el que falla AFIRMA libre un arma que es de Grace—
y de que la guarda que en discos cubre ese caso no sirve al principio de una pasada, porque no hay
filas contra las cuales chocar.

**La pasada corrió el 2026-09-08** — números y hallazgos en
[`audit/censo_armas_20260908.md`](../../../../audit/censo_armas_20260908.md). `inventory_weapons` pasó de
0 a **28 filas**, 28 PJs de 51, con `integrity_check` ok. El contador del header dice **185**, no
las 57 de la captura vieja, y se recorrieron sólo los rangos **S y A**.

La pasada refutó una premisa del diseño: el bucket C descartaba un arma que ya figuraba en otro PJ
leyéndolo como error de badge, y los W-Engines son **fungibles** — el refinamiento lo probó (Sunna
P3 contra los P5 de Lucía y Yuzuha en el mismo modelo). Arreglado en `6f1a1cb`.

Queda, en este orden: **segunda pasada corta** por los 4 engines duplicados (recupera 9 filas), los
tiles de **rango B**, y la **migración curada** de las ~7 armas fuera de catálogo, que ya están
listadas con su nombre español de pantalla.

## 3. Segundo censo de discos

Daniel declara ~400 y hay 384. Sirve para tres cosas a la vez: completar la plantilla, cerrar la
brecha, y **medir otra vez la responsividad** con los arreglos de esta semana ya puestos (guard
por superficie, adopción de marcados, resolvedor de sets por margen).

## 4. Thresholds — ⚠️ anotado por Daniel el 2026-09-05

> *"si captura el sistema pero no sugiere nada"*

El sistema captura los discos correctamente pero **no emite recomendaciones**. Hay que revisar
`agent_score_thresholds` (defaults 0.75 equipar / 0.50 stock) y el camino
`scoring → score_normalizer → recommender`. Sospecha inicial: los thresholds por PJ nunca se
sembraron con datos reales, o el score normalizado no llega al piso nunca.

Es lo que convierte al sistema de "registro" en "asistente", así que es el tramo de más valor
funcional pendiente.

## 5. Toasts con valor real + UI/UX

Con los thresholds andando, los toasts pasan a decir algo accionable. Ahí entra la implementación
de los mockups de Claude Design (`Documentacion/Interfaz/`), que están hechos y sin portar.
Relacionado: la deuda de UI ya anotada (íconos y tipografía muy chicos en el toast).
