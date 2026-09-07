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
[`2026-09-06_FEAT_Los_tres_verbos_la_DB_sigue_al_juego_sola.md`](./2026-09-06_FEAT_Los_tres_verbos_la_DB_sigue_al_juego_sola.md).

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

## 2. Censo de armas / W-Engines 🟡 IMPLEMENTADO, falta la pasada en vivo

Detalle en [`2026-09-06_FEAT_Censo_de_W_Engines_el_inventario_de_armas_existe.md`](./2026-09-06_FEAT_Censo_de_W_Engines_el_inventario_de_armas_existe.md).

`inventory_weapons` existía con **0 filas** y sin repo ni syncer. Ahora hay migración (`_26`),
`InventoryWeaponRepo`, `WeaponSyncer`, contador del header parametrizado, `DiscCensus`
generalizado a `InventoryCensus` y reporte de cierre. 73 tests nuevos, 15 sabotajes.

**Lo que v1 escribe:** sólo las armas cuyo dueño se NOMBRA. La lectura de dueño de S30 mide 8/10 y
el caso que falla *afirma* que un arma está libre siendo de alguien — nombrar es fiable, negar
dueño no. Lo demás se registra como brecha con su causa.

**Decisión de Daniel:** el inventario primero (57 tiles), y con el número medido se decide si hace
falta la pasada por las 51 fichas de PJ. Las ~5 armas fuera de catálogo que la pasada descubra
entran por una migración curada al final.

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
