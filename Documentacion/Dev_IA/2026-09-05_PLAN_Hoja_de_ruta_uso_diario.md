# Hoja de ruta del uso diario (acordada 2026-09-05)

> Daniel empezó a usar el sistema a diario para su farmeo. Este es el orden que pidió, con lo que
> cada tramo requiere y lo que se encontró al empezar el primero.

## Contexto operativo que cambia las prioridades

- **El farmeo es por pilas: ~5 corridas por día como máximo.** El volumen de discos nuevos es
  bajo, así que el costo por disco no es el problema; la **consistencia** sí.
- La app se abre y se cierra a mano (el watcher está escrito pero **no instalado**).
- Inventario real declarado por Daniel: **~400 discos**; la DB tiene 384.

---

## 1. Cada disco farmeado entra a la DB ⬅ EN CURSO

Hoy el flujo de farmeo (S13 → S2 → S3) es **display-only**: detecta el drop, lo parsea entero y
lo muestra, pero no escribe. Verificado en la sesión del 2026-09-05: 7 drops de Rosa espinosa y
Hado emplumado detectados, **0 líneas de persistencia**, DB sin cambios.

**La maquinaria ya existe.** `persist_s17_disc` persiste discos sin dueño desde el 2026-08-18
(`_persist_disco_libre`): dedup por identidad completa, se abstiene si la identidad choca con un
disco EQUIPADO (el caso del gemelo) y avisa ante ambigüedad. Así entraron los 79 libres del censo.
Un drop es un disco **sin dueño por definición** — acaba de caer en la mochila.

### ⚠️ Dos fugas que hay que resolver para que esto sea correcto

Persistir el drop, solo, hace que la DB **crezca y nunca decrezca**:

1. **Subir de nivel cambia la identidad.** Un drop a Nv0 tiene 3 substats (el 4º se desbloquea a
   +3). La identidad de dedup incluye nivel y substats, así que el mismo disco físico a Nv15 con
   4 substats **no matchea su propia fila** ⇒ segunda fila. El flujo de mejora (S10) existe y está
   validado, pero es display-only: no actualiza la fila.
2. **Desmontar no borra.** La bitácora de desmontaje (S11/S24/S25) está cerrada y validada, y
   deja explícitamente la **DB intacta**. Un disco farmeado, guardado y después desmontado queda
   como fila fantasma para siempre.

Hoy la DB refleja la realidad porque se re-censó desde cero. Sin cerrar estas dos, cada día de
farmeo la aleja un poco.

**Decisión pendiente de Daniel:** persistir igual y reconciliar con censos periódicos (lo barato),
o cerrar antes el ciclo de vida (mejora actualiza + desmontaje borra).

### Lo que no se puede recuperar

Los drops del 2026-09-05 **no se pueden migrar retroactivamente**: el log guarda set/slot/main/
nivel pero **no los substats**, y sin ellos no hay identidad. Entran cuando Daniel recorra el
inventario.

## 2. Censo de armas / W-Engines

El inventario de armas arranca de cero. El parser S30 está cerrado (6 campos, 6/6) y S26/S29
también. Falta el equivalente al censo de discos: cobertura, dueño, y persistencia.

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
