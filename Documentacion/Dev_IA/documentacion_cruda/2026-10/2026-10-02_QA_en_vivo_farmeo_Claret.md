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
