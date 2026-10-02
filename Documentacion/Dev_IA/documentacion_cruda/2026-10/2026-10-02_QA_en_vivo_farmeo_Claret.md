# QA en vivo · farmeo de Claret Flint con la app escribiendo (2026-10-01/02)

Primera sesión larga con el **paso 8** (sugerencias en vivo) y la app en **modo escritura**:
farmeo por baterías (S21/S22), afinación (S4/S5), mejoras (S10), equipamiento (S17), inventario
(S9) y desmontaje (S11). ~23:35 → 00:23. Log: `app.log` de esa ventana. Correcciones de la DB:
`audit/correcciones_farmeo_claret_20261002.md`.

**Resultado para Daniel:** Claret terminó con su build completa y el slot 6 **DEF%** que le faltaba
(#417); slot 4 cambiado por uno con DEF% +2.

## Lo que anduvo

- **Lectura de discos:** S22 (panel DETAIL), S5, S6/S7, S9, S17 y S10 leyeron set, slot, main,
  substats y rolls sin errores de OCR en los stats en toda la sesión.
- **Mejoras confirmadas por la afinación (S5→S10→S5):** el resumen y la confirmación salieron bien
  (Rosa espinosa slot 4 y slot 5, 0→15).
- **S17** registró los cambios de equipo de Claret por (PJ, slot); el desmontaje dio de baja lo que
  estaba en la DB (2 + 1) y separó lo que no (19 + 10 + 4) sin ambiguos.
- **Paso 8:** ningún error del cálculo de la sugerencia (`[sugerencia] falló` = 0).

## Bugs encontrados (por orden de gravedad)

1. **La confirmación de una mejora compara sólo set + slot** (`_same_disc` / `_same_disc_canon`,
   `sync_upgrade.py`). Con un disco del mismo set y slot equipado en el PJ que se mira después, ese
   disco confirma la mejora y `actualizar_por_mejora` le escribe sus stats a la fila mejorada.
   Pasó **dos veces** (#408 ← stats de #396; #406 ← stats de #397). → SPEC punto 4.
2. **Mejorar desde el "Ver" (S6/S7) o mirar el disco después en el inventario (S9) no confirma
   la mejora** → la fila vieja queda en Nv 0 y S9 inserta otra: **fantasma** (#409, #411, #413).
   → SPEC puntos 3 y 5.
3. **Un disco recién equipado visto como LIBRE se inserta otra vez** (#419, 5 s después de que S17
   lo guardara en #402). La guarda "libre con la identidad de un equipado" frenó el caso del slot
   6 (#416) pero no éste. **Sin diagnosticar**: comparar las dos líneas del log antes de teorizar.
4. **Badge de dueño mal leído en S9:** el Rosa espinosa de Claret se leyó con el badge de Sunna →
   `s17_move` a Sunna y #33 desplazado. S17 lo devolvió a Claret, pero #33 quedó desplazado.
   (Un mismo disco en S9 y S17 con dueños distintos: S17 manda, pero el desplazado no se repara.)
5. **El cambio de slot 6 (#416 → #417) no se registró:** el check del pendiente vio un disco que no
   coincidía y se abstuvo. Correcto por RNF-02, pero el usuario lo vio como "no lo detecta".
6. **Título "(1)" del Obtenido** — ARREGLADO en la sesión (`c404d3b`): el OCR se comía el "1".
7. **Grilla de S22 cierra una corrida con "0 discos S"** después de haber mostrado ≥3 (00:06:19).
   Display-only.

Corregido en la DB (con la app cerrada, ensayo en copia, backup, FK e integridad): ver el audit.

## Lo que Daniel pidió que falta: "mejorá este disco para ver si le sirve a un PJ"

> "siento que si recomendaba guardar discos pero le faltaba la predicción de 'mejora este disco
> para ver si le sirve a un pj' — como pudiste ver realicé eso varias veces"

**Lo que hace hoy el motor** con un disco < Nv 15 (`_recomendar_por_potencial`, casos 6/7, R11-R14):
calcula el **valor esperado** subido y

- **MEJORAR → PJ** si lo esperado le gana a lo que ese PJ lleva en el slot (R12);
- **GUARDAR (sin subir)** si sirve pero lo esperado no le gana a nadie;
- descartar si tiene dos líneas muertas (R13).

Y R14 (septiembre) dice: *"Daniel igual sube todo para ver el valor final, pero la recomendación es
frenar"*. O sea: **el "subir para ver" quedó fuera del motor a propósito.** Lo que Daniel pide ahora
lo trae adentro.

**El caso que lo muestra:** Rosa espinosa slot 4 Prob. Crítica, Nv 0 (DEF% 4,8 · ATK% 3 · Maestría
9). Por lo esperado no le ganaba al slot 4 de Claret → no decía MEJORAR. Subido cayó DEF% +2 y PV% +2
y **sí le ganó**: Daniel se lo equipó.

**Idea a diseñar (no decidida):** además de lo esperado, la **probabilidad de que le gane** a lo
que el PJ lleva — p. ej. "PROBAR → Claret (≈ 1 de 3)". Se puede enumerar: 5 mejoras hasta el 15,
cada una a uno de los substats. Lo que **no** sabemos es la probabilidad de cada substat cuando se
desbloquea el 4.º, ni si el reparto de rolls es uniforme: RNF-02, no inventarla — o se toma de una
fuente, o se acota (peor/mejor caso) sin pesos.

## Siguiente

1. Aprobar el SPEC de S22 (`2026-10-02_SPEC_Obtenido_guarda_los_discos.md`, puntos 1-5) y su plan.
2. Diagnosticar el bug 3 con el log.
3. Decidir con Daniel la predicción de "probar".

---

# Sesión 2 · QA en vivo del SPEC del "Obtenido" (2026-10-02, 10:22 → 11:58)

App en modo escritura con los 5 commits del SPEC activos (`d11a0b2`…`13590b7`). Correcciones de la
DB al cierre: `audit/correcciones_farmeo_claret_20261002.md` §4.

## Lo que se verificó en vivo

| paso del SPEC | visto | resultado |
|---|---|---|
| S22 guarda lo que se clickea | ~20 `s22_drop_insert` (#420…#461) | ✅ |
| volver al Obtenido no reinserta | "ya guardado en esta tanda" (#422, #426, #461) | ✅ (salvo #444, ver bug 1) |
| la mejora desde el "Ver" se confirma | #420, #443 | ✅ |
| S9 confirma la mejora | #432, #434, #449, #423, #404 | ✅ (2 s en el camino feliz) |
| S17 no pisa la fila con otro disco del mismo set | Remielle s3 (#3 → #463), Claret s1 (#396 → #465) | ✅ el viejo conserva SUS stats |
| el libre recién equipado se adopta | — | ❌ no se armó el aviso (bug 4) → duplicados #443/#463, #404/#465 |
| refrescos de S17 sin cambio | Remielle 6/6, Claret 6/6 | ✅ `s17_update` |

## Bugs (en orden de lo que cuestan en datos)

1. **El Obtenido leyó un roll de menos** ("Maestría de Anomalía 18" con 0 rolls) → la memoria de la
   tanda no reconoció al #443 mejorado → #444. **ARREGLADO** en la sesión (`b177e4e`): rolls desde
   el valor con `VALOR_POR_MEJORA`. Decisión de Daniel ("hacé el 1").
2. **Mejoras que no se confirman** → la fila queda vieja (#422, #426, #431). Tres causas distintas:
   - S10 leyó el PRE ya en Nv 3/4 (mejora rápida: 2-3 s en S10) → "no subió de nivel";
   - el "Ver" descartado por confianza 0,69 (< 0,70) dos veces seguidas;
   - **la captura se reinició** (10:36:36, 10:39:25, 10:53:12; `controller.stop`) y el pendiente
     se perdió. ¿Lo hizo Daniel o algo lo dispara solo? Sin confirmar.
   Daniel: "a veces no detecta la mejora porque no me dan materiales de vuelta" — a contrastar con
   estas tres causas antes de teorizar otra.
   **Arreglo propuesto (no hecho):** cuando el Obtenido muestra un disco de la tanda más crecido,
   actualizar esa fila (es de la tanda y `es_el_mismo_disco` lo confirma).
3. **Demora de 37 s** en confirmar el #443 (el "Ver" lo vio en Nv 15 a las 10:33:27, la fila se
   actualizó a las 10:34:04): mientras tanto la card mostró DESCARTAR sobre el Nv 0.
4. **La grilla de selección leyó "equipado · dueño incierto" un disco LIBRE** (#443, 10:55:21) → no
   se armó "libre → PJ", S17 hizo `s17_swap` y el disco quedó dos veces. Pasó también con Claret
   s1 (#404 → #465). Es el caso común de "equipar lo que sugiere el motor".
   Opciones: armar el aviso también con "equipado · dueño incierto" + botón "Reemplazar", o leer
   mejor el badge de la grilla.
5. **El resumen de la mejora no muestra el substat nuevo** (`_roll_diff`: entra con 0 rolls → delta
   0) → "nivel 0→4 · sin cambio de roll" con DEF% recién destrabado. Sólo el mensaje.
6. **Stats de Claret en S18** (10:58:53): Prob. Crítica 112,3 % (¿12,3 %?), ATK y Recarga sin leer,
   y el log igual dice "11/11 stats capturados". Velina, leída justo antes, salió perfecta →
   hipótesis: el perfil de Armero (LAC/AF) corre las filas.
7. **Ruido conocido:** el "Obtenido" de la moneda del evento (gastar baterías) entra como S24 y se
   abstiene ("sin tanda de desmontaje abierta"). Correcto; aclarado por Daniel.

## Siguiente

Prioridad por datos: bug 4 (duplicado en cada equipamiento sugerido) y bug 2 (el arreglo propuesto
del Obtenido + diagnosticar los reinicios). Después 3, 6 y 5.
