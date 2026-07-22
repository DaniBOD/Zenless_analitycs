# IMPL — Disco libre equipado → toast "AHORA EN \<PJ\>" (S17)

**Fecha:** 2026-07-22
**Estado:** ✅ IMPLEMENTADO · ⏳ **QA en vivo pendiente**
**Hermano de:** [Reemplazo de disco S23](./2026-07-19_IMPL_Reemplazo_Disco_S23.md) (cerrado 2026-07-20)
**Supera a:** [PLAN](./2026-07-22_PLAN_Disco_Libre_Toast_Equipado.md) (se equivocó de pantalla — ver §1)
**Relacionado:** [SPEC Invariante equipado/asignado](./2026-07-22_SPEC_Invariante_Equipado_Asignado.md)

---

## 0. Qué hace

Detecta que el usuario **equipó un disco que no era de nadie** y lo avisa con un toast violeta
**"AHORA EN \<PJ\>"**. Igual que el reemplazo, es **observacional**: no escribe la DB y sale en
read-only.

Señal, en palabras de Daniel:

> "el sistema debe detectar cuando aparezca el badge al lado del nombre del slot además de que si se
> equipó el botón pasaría a desequipar, ese es otro factor para detectar el cambio"

---

## 1. La corrección que achicó el trabajo: es S17, no S6/S7

El plan previo asumía **S6/S7**. Antes de escribir código se corrió el detector sobre los propios
fixtures:

| carpeta | clasificación real |
|---|---|
| `17_Inventario_Disco_Vista_Individual_libres` | **11/11 → S17** (conf 1.00, `s17_personalizacion_pistas.png`) |
| `04_Inventario_Disco_Vista_Individual` | 13 → S17, 2 → S7, 1 → S6, 1 → S12 |

Los nombres de carpeta son **etiquetas organizativas, no estados**. El error fue leerlos como si
nombraran la pantalla.

**Lección: verificar el estado con el detector, no deducirlo del nombre del archivo.**

El impacto fue a favor. S17 ya tenía todo lo que el plan proponía construir:

| pieza | S6/S7 (lo asumido) | S17 (la realidad) |
|---|---|---|
| handler | one-shot (`_processed_disc_state_code`) | **continuo con aggregator** |
| latch de identidad | se **resetea** al entrar (`monitor.py:952`) | **se preserva** (S17 es la excepción) |
| dueño por badge | no se calcula | **`_assign_s17_pj` + `equip_libre` ya calculados** |
| check del reemplazo | — | **`_check_swap_owner` ya corriendo ahí** |

Quedaron sin objeto la fase de "capturas del después" y toda la de detección de badge.

---

## 2. Las dos señales (verificadas antes de implementar)

### A — badge junto al pill de nivel

No está a la derecha del **título** sino a la derecha del pill **"Nivel X/15"**, una línea más abajo.

`crop_s17_assigned_avatar` ([`parser_disc_s17.py:614`](../../app/core/parser_disc_s17.py)) ya lo
recortaba, y funciona **tal cual** — probado sobre los fixtures, 3/3:

| captura | pill | crop |
|---|---|---|
| `17/Ejemplo_2_(equipar)` | OK | `None` → LIBRE |
| `17/Ejemplo_1_(reemplazar)` | OK | `None` → LIBRE |
| `04/Ejemplo_1` | OK | avatar 56×56 → OCUPADO |

Cero código de recorte nuevo.

### B — botón de acción

**Corrección de Daniel:** el botón **no habla del disco, habla del slot destino**.

| botón | significado |
|---|---|
| `Equipar` | disco libre → el PJ tiene ese slot **vacío** (no desplaza) |
| `Reemplazar` | disco libre → el PJ ya tiene uno ahí → **habrá un desplazado** |
| `Desequipar` | el disco ya lo lleva puesto este PJ |

OCR limpio (conf 1.00 en los 3 fixtures) con posición estable:

| `cx_norm` | botón |
|---|---|
| 0.639 | "Desequipar rápido" ← **ignorar** |
| **0.772** | **el de acción** |
| 0.905 | "Mejorar" ← ignorar |

⚠️ **La trampa:** "Desequipar rápido" es otro botón y aporta un `desequipar` fantasma. Si se
eligiera por presencia del texto en vez de por posición, **todo disco libre leería "desequipar"** y
el check daría por equipado algo que nunca se equipó. Hay un test dedicado a esto.

### Por qué las dos y no una

Cada una tapa el agujero de la otra:

- **LIBRE es la lectura más frágil del sistema de badges.** El 2026-07-19 hubo que cambiar la regla
  a *"presencia gana a LIBRE"* porque la cara de Jane se leía como texto. Un falso LIBRE acá
  dispararía un toast fantasma.
- **El botón** es texto de posición fija (mucho más confiable) y `Equipar`/`Reemplazar` solo salen
  en discos libres → confirma la ausencia de badge por vía independiente. Pero **no dice quién** es
  el dueño.

Para un falso positivo tendrían que fallar **las dos a la vez y de forma coherente**.

---

## 3. Implementación

### 3.1 `read_s17_action_button` (`app/core/parser_disc_s17.py`)

ROI de la barra inferior (`y∈[0.915,0.995]`, `x∈[0.55,0.99]`) → se queda con la línea de
`cx_norm∈[0.72,0.83]` → match por **prefijo** normalizado contra `("desequipar", "reemplazar",
"equipar")`, en ese orden: `desequipar` debe ganarle a `equipar`, que lo contiene como sufijo.

El filtro de basura del panel (`parser_disc_s17.py:763`) **no se tocó** — sigue descartando estos
textos para el parseo de stats, que es lo correcto. Esta es una lectura aparte con su propio ROI.

### 3.2 Gate RNF-06 de la relectura (`_refresh_action_button`)

Es una llamada **extra** a OCR, así que no corre por ciclo. Se relee solo cuando cambia
`(identidad del disco, libre?, badge presente?)`. Las tres ya se computan cada ciclo y son baratas
(el badge es un crop + Canny), y entre las tres cubren las únicas transiciones que pueden cambiar el
botón: abrir otro disco, o equipar/desequipar el que se mira.

### 3.3 Pendiente + check (`app/core/monitor.py`)

Se **reusó el esqueleto del S23** en vez de duplicarlo: `_pending_swap` ganó `origin_kind ∈
{"pj","libre"}` y un solo slot de pendiente — las dos acciones son mutuamente excluyentes y la
última intención manda.

- **`_arm_libre_pending`** — arma si `equip_libre` ∧ botón ∈ {equipar, reemplazar} ∧ hay latch.
  Armar no afirma nada; el que decide es el check.
- **`_check_libre_equipado`** — desenlaces `cambió` / `otro` / `incierto` / `solo badge`, todos
  logueados por flanco. Solo `cambió` dispara y consume (RNF-02).

**Orden en el ciclo continuo: check ANTES que armado.** Si armara primero, el pendiente recién
creado podría confirmarse en el mismo ciclo contra su propio estado inicial.

**Dos diferencias deliberadas con el pendiente de S23:**

1. **Identidad COMPLETA** (`_disc_identity`: set, slot, main, {substat+rolls}), no solo set+slot.
   Sin esto hay un falso positivo concreto: mirás un Jazz Caótico slot 1 libre, **no lo equipás**, y
   más tarde entrás a un PJ que ya tiene uno puesto → *"antes LIBRE, ahora ese PJ"* → toast fantasma.
2. **Muere al cambiar de PJ.** El diálogo S23 es un compromiso explícito y por eso su pendiente vive
   hasta consumirse; mirar un disco libre no compromete nada — se equipa al PJ que estás mirando, en
   la misma visita.

A diferencia del reemplazo **no** se marcan `swap_origin_hint`/`swap_fresh`: no hay fila de origen
que mover. La persistencia sigue su camino sin pistas nuestras.

### 3.4 Toast

Variante `equipado` en `tokens.py`: **label `"AHORA EN"`, color `PURPLE`** — misma familia que
REEMPLAZADO, porque lo que los agrupa no es el verbo sino que **ya ocurrieron**.

**Por qué no "EQUIPADO":** en un toast de 380 px, `EQUIPADO` y `EQUIPAR` (la recomendación) difieren
en dos letras. Mal lugar para apoyar toda la distinción. `AHORA EN` describe el resultado.

**Por qué el nombre del PJ va en el body y no en el label:** el header tiene ~87 px de holgura antes
del micro-badge, y `"AHORA EN ORFIA Y MAGAS"` se los come. El body ya pinta avatar + nombre, así que
se lee de corrido: *AHORA EN → \[avatar\] Velina*.

`_paint_body_equipped`: thumb centrado + set/slot, **un solo PJ** a la derecha ("EQUIPA"), "SIN
DUEÑO" atenuado a la izquierda, una sola flecha. `show_replacement` y `show_equipped` comparten
`_show_confirmation` (posición, thumb, fade, timeout); lo único que cambia es el body.

Ruteo: el monitor manda `kind` en el evento → `_on_replacement_from_monitor` emite `disc_equipped`
o `disc_replaced` → `main.py` conecta cada una a su handler.

### 3.5 Corrección: el toast REEMPLAZADO afirmaba algo falso

Desde el rediseño observacional del 2026-07-20 el toast sale **aunque la DB no se escriba** (en
read-only, o si la persistencia no encuentra la fila). Pero seguía diciendo:

| dónde | decía | dice ahora |
|---|---|---|
| footer izq | `EQUIPAMIENTO SINCRONIZADO` | `REEMPLAZO OBSERVADO` |
| footer der | `inventory_discs ✓` | `S23 → badge ✓` |
| micro-badge | `✓ SINCRONIZADO` | `✓ OBSERVADO` |

El toast afirma lo que se **vio**, no lo que la DB guardó. El de equipado usa
`EQUIPAMIENTO OBSERVADO` / `badge + botón ✓` / `✓ OBSERVADO`.

---

## 4. Archivos

| Archivo | Cambio |
|---|---|
| `app/core/parser_disc_s17.py` | `read_s17_action_button` + logger de módulo |
| `app/core/monitor.py` | `origin_kind`; `_refresh_action_button`; `_arm_libre_pending`; `_check_libre_equipado`; ruteo en `_check_swap_owner`; `kind` en el evento; reset del botón |
| `app/ui/tokens.py` | variante `equipado` |
| `app/ui/toast.py` | `show_equipped`; `_show_confirmation` (extraída); `_paint_body_equipped`; textos honestos |
| `app/ui/controller.py` | señal `disc_equipped`; ruteo por `kind` |
| `app/main.py` | `_on_disc_show_equipped_toast` |

**Sin cambios:** `sync_equip.py`, `repositories.py`, `asset_resolver.py`. **No escribe la DB.**

---

## 5. Tests

| Archivo | Qué fija |
|---|---|
| `test_parser_boton_s17.py` (nuevo, 9) | lectura del botón sobre **capturas reales**; que "Desequipar rápido" no se cuele; selección por posición y no por orden; degradación ante OCR roto |
| `test_monitor_equipado.py` (nuevo, 17) | armado y sus guardas; las dos señales; abstención con una sola; disco gemelo; muerte por cambio de PJ; flanco del log; gate de relectura |
| `test_toast_equipado.py` (nuevo, 6) | variante; **que no se confunda con `equipar`**; render con nombre largo |
| `test_reemplazo_readonly.py` (+2) | el toast de equipado sale en read-only; el ruteo `kind` no mezcla los dos |
| `test_monitor_sustitucion.py` (ajuste) | el evento ahora lleva `kind: "reemplazo"` |

---

## 6. QA en vivo pendiente (READ-ONLY)

`powershell -File tools\qa_launch.ps1 -FromSource -NoFocusGate -ReadOnly`

| # | Caso | Esperado |
|---|---|---|
| A | slot **vacío** → equipar un disco libre | `[equipado] check dueño · … · CAMBIÓ ✓` + toast violeta "AHORA EN" |
| B | slot **ocupado** → botón "Reemplazar" | mismo toast (decisión: no se menciona al desplazado) |
| C | abrir un disco libre y **volver sin equipar** | log `incierto`/`solo badge`, **sin** toast |
| D | reemplazo entre PJs (S23) | sale **REEMPLAZADO**, no "AHORA EN" |

Verificar además `[readonly] S17 NO persiste` y que el sha256 de `db/danibod_zzz_v2.db` **no cambió**.

---

## 7. Fuera de alcance

- **Desequipar** (dejar un slot vacío) — transición inversa, reusa todo esto.
- **Escritura a la DB** — el invariante equipado/asignado sigue bloqueado hasta re-sincronizar
  (ver la SPEC).
- **S6/S7 real** (el "Ver" desde inventario/tienda) — sigue one-shot y sin dueño.
