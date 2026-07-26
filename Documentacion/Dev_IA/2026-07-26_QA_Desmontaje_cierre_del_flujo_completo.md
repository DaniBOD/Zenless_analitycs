# QA en vivo · el desmontaje cierra el flujo completo

**Fecha:** 2026-07-26 · **HEAD:** `a6585f2` · **Modo:** `-FromSource -ReadOnly -NoFocusGate`

Segunda pasada. Cierra el **bloque 6**, que era lo único que quedaba sin probar contra el juego:
el commit, el toast y la bitácora. Con esto la bitácora de desmontaje queda **validada de punta a
punta en vivo**.

---

## 1. La tanda, tal como salió

```
15:03:14  [estado] S17 → S11 (conf=0.97)
15:03:14  [desmontaje] tanda abierta
15:03:27  [desmontaje] +1 → 1/300 · Firmamentollameante (2) Nv0 · ATK 79.0 · DEF% 4.8 / DEF 15.0 / Prob. Crítica 2.4
15:03:35  [desmontaje] +1 → 2/300 · Salón huracanado (2) Nv0 · ATK 79.0 · HP 112.0 / ATK% 3.0 / Maestría de Anomalía 9.0
15:03:44  [desmontaje] +1 → 3/300 · Salón huracanado (2) Nv0 · ATK 79.0 · Maestría de Anomalía 9.0 / Perforación 9.0 / ATK% 3.0
15:03:50  [desmontaje] −1 → 2/300 · destildado: Salón huracanado
15:03:57  [desmontaje] +1 → 3/300 · Salón huracanado (2) Nv0 · ATK 79.0 · Perforación 9.0 / DEF% 4.8 / DEF 15.0
15:04:08  [desmontaje] scroll detectado — las celdas dejan de identificar al disco
15:04:12  [estado] S11 → S25 (conf=1.00)
15:04:12  [desmontaje] confirmación de grado S · 3 declarados · esperando el Obtenido
15:04:39  [estado] S25 → S24 (conf=1.00)
15:04:40  [desmontaje] tanda cerrada · 3 desmontados (3 con datos, 0 sin)
15:04:40  [desmontaje] → audit\desmontajes\20260726_150440_407166_desmontaje.json
```

**Toast violeta emitido, uno solo.** DB con **sha256 idéntico** antes y después
(`CEB152D2…6091`): la tanda no escribió una fila.

### Lo que esto confirma, más allá de "funcionó"

- **S25 detectó el diálogo a conf 1.00** en su primera exposición al juego real, y —lo importante—
  **la tanda sobrevivió**. Ése era el riesgo estructural de darle estado propio: al dejar de caer a
  S12 salía de la lista blanca de la regla de abandono y habría matado la tanda justo antes del
  commit. El test lo previó; el juego lo confirmó.
- **El destildado funciona en vivo** (`−1 → 2/300`) y el disco se rehizo después con otro
  (`seq 2` y `seq 4` en el JSON, sin `seq 3`): la numeración deja el rastro del que se sacó.
- **El contador es la autoridad, y se notó.** A las 15:04:08 se volvió ilegible (scroll + diálogo),
  y el conteo declarado quedó congelado en 3 — que es el número correcto y el que terminó en el
  registro. La cobertura fue 3/3.
- **`confirmacion_grado_s: true`** en el registro.

### Detalles menores, anotados sin perseguir

1. `[S24] sin resultado — Obtenido sin tanda de desmontaje abierta` sale **después** de un commit
   exitoso, mientras el modal sigue en pantalla. El gate de idempotencia funciona; el texto miente
   un poco (la tanda no está "sin abrir", está **ya commiteada**). Cosmético.
2. Al volver de S24 a S11 se abre una tanda nueva (`15:05:09 tanda abierta`) que muere por
   abandono sin registrar nada, como corresponde.
3. `material_primero: null` — las cantidades del "Obtenido" siguen sin leerse. Es la limitación
   conocida y aceptada: oráculo secundario, nunca fuente. Por eso la línea de cierre salió sin el
   `· material ×N ✓`.

---

## 2. El latido, en su primer día de trabajo

Funciona, y ya devolvió un dato que no esperábamos:

```
[hb] 20 ciclos · frames_nulos=0 · estado=S15 · tanda=- · excepciones=0
[hb] 19 ciclos · frames_nulos=0 · estado=S15 · tanda=- · excepciones=0
[hb] 34 ciclos · frames_nulos=0 · estado=S11 · tanda=- · excepciones=0
```

**~20 ciclos por minuto = 0.3 ciclos/s.** El loop está descripto como "captura rápida cada ~100 ms"
(10 fps), y en S15 corre **treinta veces más lento**.

No es un bug: en estados con handler continuo, cada iteración paga el OCR del handler, y el
`_wait_fast` de 100 ms es apenas el piso. Pero **desmiente un supuesto que estaba escrito en el
código** y que importa para el trabajo de latencia: el muestreo "rápido" de 10 fps —del que dependen
el censo de tildes de S11 y la votación del dueño en S17— **no existe en los estados que hacen
OCR continuo**.

Vale medirlo en serio antes de la fase de latencia
(`Documentacion/2026-07-10_Futuro_Latencia_GPU_Distribucion.md`). Es exactamente el tipo de
supuesto que hace que una optimización apunte al lado equivocado. Nota: `frames_nulos=0` y
`excepciones=0` en toda la sesión, así que la captura y los handlers estuvieron sanos.

---

## 3. Deuda de UI abierta

El toast **sale y es correcto**, pero está pintado a mano en Qt sin pasar por diseño. Daniel pidió
además agrandar íconos y tipografía **en todas las variantes**, con permiso explícito de agrandar
el frame si hace falta.

Medido sobre el código en producción: badge de rareza de **14 px con letra de 7 px**, logo del set
a **~37 px efectivos**, y una franja de texto de **7-8 px** (ID, micro-badge, footer) que hay que
leer *de reojo mientras se juega*.

Y un hallazgo del relevamiento: **el ícono del header nunca se implementó**. `tokens.py` define uno
por variante (`trash`, `swap`, `check`…) pero `_paint_header` dibuja solo el label de texto con un
subrayado. El chip con ícono de los mockups JSX se perdió en el port a Qt — así que parte del
"los íconos son chicos" es, literalmente, íconos que no están.

Brief completo con todas las medidas y los cuatro puntos que el diseño tiene que resolver:
`Documentacion/Interfaz/claude_design_upload/BRIEF_toast_desmontado_y_legibilidad.md`.

---

## 4. Estado del feature

**Cerrado y validado en vivo.** Lo que queda es de otra naturaleza:

- **Diseño del toast** (brief entregado, pendiente de sesión con Claude Design).
- **La baja real en `inventory_discs`**, que depende del censo de la cuenta y hoy no se hace a
  propósito: la bitácora solo registra. Cuando llegue, el matcher tiene que usar
  `identidad ∧ valores` y **reportar ambigüedad en vez de dar de baja** ante ≥2 candidatos — en
  Nivel 0 todos los rolls son 0 y la firma de identidad colapsa.
- **Medir el ritmo real del loop** (sección 2) antes de la fase de latencia.
