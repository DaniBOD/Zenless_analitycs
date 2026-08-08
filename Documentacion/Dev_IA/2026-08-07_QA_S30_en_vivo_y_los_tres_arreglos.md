# 2026-08-07 · QA en vivo de S30 — tres arreglos y el dueño del arma

> **Cómo salió:** el estado y el parseo del panel andaban. El QA encontró **un bug de silencio** y
> **un bug de ruido**, opuestos entre sí y con la misma raíz: gates mal puestos. Y sumó el dueño,
> que había quedado explícitamente afuera del hito anterior.
>
> Todo display-only. Cero escrituras a la DB.

---

## 1. Primera pasada: "reconoció el primer engine y después nada"

Ocho minutos en S30 con `frames_nulos=0`, una sola línea al entrar y silencio. **Y ninguna línea
de trabe** — que fue lo que dio la pista: si el parser fallara, `_note_stall` lo habría dicho. No
decir nada significaba que nunca se llegaba al parser.

**Causa:** el monitor re-despacha solo una lista de estados mientras seguís en la pantalla, y
**S30 no estaba**. S9 y S26 sí. Se despachaba una única vez, al entrar.

El criterio de esa lista es uno solo —*el contenido cambia sin que cambie la pantalla*— y el
inventario lo cumple de manual. Vivía como un literal dentro del loop, donde nada podía
verificarlo; se extrajo a `_REDISPATCH_STATES` con el criterio escrito y un test que fija que las
tres pantallas de selección (S9, S26, S30) estén las tres.

> **Patrón que va a volver: el síntoma de este bug es silencio SIN error.** Ante un "reconoce el
> primero y después nada", esa lista es el primer lugar donde mirar.

---

## 2. Segunda pasada: el log se había vuelto un heartbeat

Arreglado lo anterior, el log pasó al extremo opuesto: **110 líneas para 9 armas distintas**,
repitiendo la misma cada ~5 s. Daniel lo marcó de entrada — *"acuérdate que usamos logs dinámicos
en base a los cambios"*. Dos causas encadenadas, y ninguna se arregla sola:

### 2.1 La firma se comía lo que se mueve

`_S30_PANEL_SIG_ROI` era un rectángulo único sobre el panel entero, y ahí adentro estaban el
**arte 3D del arma** y la **barra de pestañas** de la bolsa. Las dos cosas cambian solas ⇒ la firma
nunca era igual dos ciclos seguidos ⇒ el gate no cortaba nunca y se re-OCReaba indefinidamente.

Es literalmente la trampa que ya había dejado mudo a S17 (el arte ANIMADO del hexágono, QA
2026-07-23). **Vale como regla: antes de firmar una región, preguntarse qué se mueve dentro.**

Y no alcanzaba con achicar el rectángulo: el nombre y el arte están **lado a lado**, y las
estrellas quedan más allá del arte. Cualquier rectángulo con nombre y estrellas tiene arte en el
medio. Por eso la firma pasó a ser **dos bandas**:

```
A · nombre + íconos, cortada antes del arte   (x 0.72-0.86, y 0.24-0.34)
B · pill + estrellas + stats, ya debajo       (x 0.72-0.96, y 0.37-0.56)
```

### 2.2 Faltaba el dedup por contenido

S26 tiene `_s26_last_log_sig` desde su hito y no se había portado. El gate de firma es de
**píxeles** y no garantiza que lo *leído* haya cambiado: cualquier temblor lo cruza. El log de
este proyecto reporta CAMBIOS, así que la línea se dedupea por contenido —incluida la tenencia—
y no por firma.

**Las dos hacen falta y ninguna reemplaza a la otra**: la firma ahorra el OCR (RNF-06), el dedup
mantiene el log edge-triggered.

---

## 3. El dueño del arma

Quedaba afuera del hito anterior por una razón concreta: en este panel el avatar **no está al lado
del pill** como en S26, sino arriba, en la fila de dos circulitos bajo el nombre — el izquierdo es
el ícono de **especialidad**, el derecho la cara del dueño.

Medido sobre los 6 fixtures:

| | dx desde `pill.x1` | dy desde `pill.y1` |
|---|---|---|
| especialidad | −32 … −38 | −64 … −102 |
| **dueño** | **+24 … +26** | −64 … −102 |

El `dy` se corre **~38 px** según si el nombre envuelve a dos líneas, aunque el pill se quede
clavado — el mismo fenómeno que corre la fila de estrellas en S26. Por eso la ventana de búsqueda
cubre los dos regímenes y el círculo se **detecta** por frame.

### La presencia va por POSICIÓN, no por nitidez

Acá está el hallazgo que no esperaba. En S26 la presencia se decide por nitidez porque el hueco
vacío del badge es un degradé, y el gap es de 11×. **En este panel ese criterio no sirve**: el
vecino es un glifo metálico con tanto detalle como una cara. Medido sobre las dos armas LIBRES:

```
nitidez del círculo derecho:  85.1  y  66.6      ← dentro del rango de los dueños reales
```

Lo que sí separa sin solape es **dónde cae el círculo**. El filtro es la banda de dx, y las dos
poblaciones ni se rozan. Presencia **6/6** sobre los fixtures, incluidas las dos libres.

> Generalizable: **una señal calibrada en una pantalla no se hereda a otra por analogía.** Lo que
> discrimina depende de qué hay al lado, no del elemento que se mide.

El recorte conserva el encuadre de `crop_detail_badge` a propósito, que es como se cosechó
`avatar_detbadge_v2` (like-with-like, Fase 5R).

---

## 4. QA en vivo, segunda corrida

Siete selecciones, **siete líneas, cero repetidas**:

```
Engranaje infernal    · S · Nv 60/60 · P2 · ATK 684 · Impacto 18%       · con dueño (sin identificar)
Petrazufre            · S · Nv 60/60 · P1 · ATK 684 · ATK% 30%          · con dueño (sin identificar)
Esplendor surcanimbos · S · Nv 60/60 · P1 · ATK 743 · Daño Crítico 48%  · la tiene Ye Shunguang
Sol exuvia            · S · Nv 60/60 · P1 · ATK 713 · ATK% 30%          · la tiene Pyrois
Última cena           · A · Nv 60/60 · P5 · ATK 594 · Recarga 50%       · la tiene Koleda
Última cena           · A · Nv 60/60 · P5 · ATK 594 · Recarga 50%       · con dueño (sin identificar)
Fósil preciado        · A · Nv 60/60 · P5 · ATK 594 · Impacto 15%       · con dueño (sin identificar)
```

*Última cena* aparece dos veces con dueños distintos: son **dos copias de la misma arma** y el
dedup las distingue porque la tenencia entra en la firma del log. Eso es el test
`test_cambiar_de_dueno_re_loguea_aunque_el_arma_sea_la_misma` ocurriendo en vivo.

### Presencia 7/7, nombre 3/7 — y por qué eso NO es un bug

Ninguna arma equipada salió como LIBRE. Lo que falta es el nombre, y la causa está medida:

```
detail   50 clases · 184 refs   ← la que usan las armas
grid     56 clases · 486 refs
row      50 clases · 365 refs
```

`detail` es **menos de la mitad** que las otras dos, con 8 PJs de una sola referencia (Antón, Ben,
Billy Estelar, Cissia, Harumasa, Lycaon, N.º 0: Anby, Rina). Con una sola ref el matcher no llega
al guard y **se abstiene, que es lo correcto** — un nombre equivocado es peor que ninguno, y el
colapso de julio ya mostró lo que cuesta.

**No es encuadre**, y el propio log lo prueba: tres armas salieron nombradas con confianza ≥0.90.
Si el recorte no matcheara la librería no habría nombrado **ninguna** — es exactamente lo que pasó
con el `row` y Remielle. El marco está bien; faltan referencias.

---

## 5. Pendiente

- **Cosechar `detail`** (segunda pasada, acordada): `-BadgeHarvest -IdDiag`, entrando **desde el
  menú de personajes** para que S15 siembre la etiqueta. Atajo específico de armas: en S26, si el
  juego ofrece *Desequipar*, el dueño es **certero sin librería** — es el PJ que estás mirando.
- Del QA quedan dos pasos: quedarse quieto sin líneas repetidas, y volver a la pestaña de discos
  para confirmar S9.
- **No lee los tiles de la grilla** — sigue siendo un arma por selección. Las 57 de una pasada son
  el tramo siguiente.
