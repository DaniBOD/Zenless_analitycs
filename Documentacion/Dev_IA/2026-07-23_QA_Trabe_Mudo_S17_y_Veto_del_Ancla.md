# QA 2026-07-23 — El trabe mudo de S17, el veto del ancla, y un bug abierto

**Sesión:** 00:44 – 02:14 (READ-ONLY)
**DB:** `ceb152d28e258a9c`, 367 discos — **byte a byte idéntica** al arrancar y al cerrar.
**Contexto:** QA en vivo del [toast "AHORA EN"](./2026-07-22_IMPL_Disco_Libre_Toast_Equipado.md)
(commit `553700c`).

---

## 0. Resumen

| # | Qué | Estado |
|---|---|---|
| 1 | **Caso B** — disco libre a slot OCUPADO | ✅ **cerrado** (toast confirmado en pantalla) |
| 2 | **Trabe mudo de S17** — 6 min sin una línea de log | ✅ **causa hallada y corregida** |
| 3 | **FP del ancla** — disco libre atribuido a Velina | ✅ **corregido** (veto por botón) |
| 4 | **Caso A** — disco libre a slot VACÍO | ⚠️ **ABIERTO**: arma bien, pero no confirma |
| 5 | Casos C y D | ⏳ sin correr |

---

## 1. Caso B ✅

```
00:47:58  [equipado] Salón huracanado slot 1 · LIBRE → Velina (pendiente · botón 'reemplazar')
00:48:02  check · sin dueño · incierto            → se abstiene
00:48:18  check · dueño Velina · botón 'desequipar' · CAMBIÓ ✓
```

Toast violeta confirmado en pantalla por Daniel. Las dos señales voltearon juntas y la abstención
intermedia funcionó. **Con la DB intocable** — que era el objetivo del diseño observacional.

---

## 2. El trabe mudo de S17 ✅

### Síntoma

El monitor pasó **6 minutos en S17 con el OCR corriendo** y el log no dijo absolutamente nada.
Ya había pasado el 2026-07-20 (8m42s) y por eso se había agregado `_note_stall` — pero esa
instrumentación cubrió **dos** de los returns silenciosos y el que estaba activo era un **tercero**.

### Cómo se acorraló

Sin el log, por descarte sobre el stdout de PaddleOCR:

- OCR corriendo cada ~4 s (`dt_boxes num: 28`) → el monitor estaba **vivo**.
- Al entrar a S17, un `dt_boxes num: 4` **una sola vez** → la lectura del botón (código nuevo)
  **sí** se ejecutaba, y su gate RNF-06 funcionaba. Descartado como culpable.
- Ningún `sin resultado` → ni `firma no calculable` ni `conf < 0.70`.

Quedaba un `return` sin instrumentar. Se instrumentó, y el log lo cantó en 15 segundos:

```
[S17] firma inestable · name=0.6/3.0  detail=1.3/3.5  hex=5.5/3.0
```

### Causa

El ROI `hex` de la firma (`x∈[0.58,0.95]`, `y∈[0.18,0.88]`) abarca el hexágono del PJ **incluido el
arte animado del centro**. Ese arte se mueve solo → la firma cambia → `_is_new_s17_disc` da True →

```python
self._disc_aggregator.reset()
self._disc_agg_cycles = 0      # ← el techo vuelve a CERO
```

…y como el techo nunca se alcanza, el disco nunca madura y el handler devuelve mudo:

```python
if not (mature or ceiling):
    return          # ← sin log
```

**Un bucle perfecto de silencio.** Explica también los 8m42s del 20 de julio: es el mismo trabe.

### Arreglo

`_hex_center_mask()` anula el centro (círculo en `(0.42, 0.45)` del ROI, radio `0.23`) antes de
comparar. Los 6 círculos de slot —lo único que esa componente aporta— están a ≥0.24 del centro, así
que la detección de cambio de slot queda intacta. Hay un test que prueba **las dos mitades**: que el
centro deje de contar y que el borde siga contando.

**Verificado en vivo:** `Disco detectado` a los 8 s de entrar a S17, sin un solo `firma inestable`.

### Instrumentación nueva (para que no vuelva a ser mudo)

- Contador de **resets encadenados sin emisión** → distingue navegar entre discos (resets con
  emisión de por medio) de una firma inestable (resets encadenados). Umbral 3.
- Al cruzarlo, **una sola** línea con el desglose por componente — dice **cuál** ROI es el culpable
  en vez de hacer adivinar.
- `_note_stall` en el return de madurez, gateado por ciclos para no ser ruidoso.
- Archivo `app/tests/unit/test_monitor_trabe_mudo.py` (7 tests).

### ⚠️ Error propio en el camino

La primera versión usó el scope `"S17"` para el trabe de firma — **pero ese scope lo limpia el
chequeo de confianza en cada ciclo** (el parse anda bien; lo que falla es la firma). Resultado:
nota/destrabe alternando a varios Hz, **log inundado**. Corregido con scope propio (`S17/firma`),
que solo cierra la emisión real. Hay test de regresión.

---

## 3. El FP del ancla ✅ (lo encontró Daniel)

### Síntoma

Con el **slot 1 de Velina vacío**, al entrar al detalle el sistema atribuyó el primer disco a Velina:

```
02:02:01  [S17] asignado a 'Velina' (latch; sim=equipado)
02:02:01  [readonly] ... asignado=Velina          ← falso: el disco está LIBRE
```

### Causa

El **ancla de flujo** asume una estructura del juego: *"el primer disco al abrir un slot es el
equipado por el PJ"*. Con el slot **vacío** no hay equipado, y el primero que se muestra es un
candidato libre.

Y el badge **no podía corregirlo**: su **ausencia** no cuenta como evidencia en contra — es la regla
*"presencia gana a LIBRE"* (5R.L.8, 2026-07-19), puesta justamente para evitar falsos LIBRE. Así que
el ancla ganaba por default y no había nada que la contradijera.

### La observación de Daniel, y su alcance real

> "en el caso de que aparezca en el primer disco detectado 'equipar' además de que no detecta el
> badge significa que el disco está libre"

Correcto — y el botón resuelve **los tres** casos, no solo el del slot vacío:

| botón | significa | ¿el ancla vale? |
|---|---|---|
| `Desequipar` | este disco **lo lleva puesto** el PJ | ✅ sí |
| `Equipar` | el slot está **vacío** → no hay equipado | ❌ no |
| `Reemplazar` | el slot tiene otro disco → este es **candidato** | ❌ no |

O sea: el botón no es un parche para el slot vacío, **es una afirmación directa sobre si el disco en
pantalla es el equipado de ese PJ**. Cubre también los otros dos modos de falla que el propio código
ya documentaba (navegar dentro del slot, re-entrar a S17 sobre un candidato).

### Arreglo

**Guard, no reemplazo**: el ancla se veta solo ante evidencia positiva en contra
(`equipar`/`reemplazar`). Si el OCR no leyó el botón (`None`), el comportamiento es el de siempre.
La lectura se movió **dentro de `_assign_s17_pj`**, antes de que el ancla decida.

**Verificado en vivo** — mismo escenario, antes y después:

| | antes (02:02:01) | después (02:11:57) |
|---|---|---|
| ancla | `asignado a 'Velina'` ❌ | **vetada por el botón** ✅ |
| badge | *(sin voz)* | `[grilla] disco LIBRE` |
| persistencia | `asignado=Velina` | `PJ no confiable — no se persiste` |

---

## 4. ⚠️ BUG ABIERTO — el caso A no confirma

### Síntoma

Slot vacío, disco libre. **Arma bien** (es lo que nunca habíamos podido probar):

```
02:11:57  [equipado] Salón huracanado slot 1 · LIBRE → Velina (pendiente · botón 'equipar')
```

Daniel lo equipó. **El sistema no lo detectó como asignado** — el último log siguió diciendo LIBRE y
el toast nunca salió:

```
02:12:18  [S17] asignado a 'Velina' (latch; sim=voto=latch)     ← el badge SÍ lo vio
02:12:18  check · LIBRE → Velina · botón 'equipar' · solo badge  ← abstención
(nada más hasta 02:14:31 Monitor detenido)
```

### Diagnóstico

El **gate de relectura del botón** es demasiado grueso:

```python
key = (self._disc_identity(merged), bool(badge_present))
```

Al equipar, la identidad del disco **no cambia** (es el mismo disco) y `badge_present` **ya estaba en
True** (por el voto del badge previo). Con la clave inmóvil, el botón **nunca se relee** y queda
cacheado en `'equipar'` para siempre. El check exige `botón == 'desequipar'` → se abstiene sin parar.

Que el desenlace `solo badge` se loguee **una sola vez** (flanco, RNF-06) hace que después de esa
línea el log quede en silencio — lo que se vio.

**Nota:** la abstención fue lo correcto (dos señales que no coinciden ⇒ no afirmar). El bug no es el
check, es que **una de las dos señales se congeló**.

### Arreglo propuesto (para mañana)

**Mientras haya un pendiente abierto, releer el botón en cada ciclo.** Está acotado —solo corre
cuando hay algo que confirmar, que es exactamente cuando la respuesta importa— y fuera del pendiente
se conserva el gate actual. Alternativa peor: meter el dueño votado en la clave (sigue siendo un
proxy indirecto de "el botón pudo cambiar").

---

## 5. Otros hallazgos operativos

- **`TaskStop` no mata la app**: termina la shell, no el proceso Python hijo. Por eso una relanzada
  salió con *"Ya hay una instancia corriendo"* y se siguió viendo el código viejo durante un rato.
  Forma correcta: identificar el PID por línea de comando exacta
  (`CommandLine like '*Zenless_analitycs*app.main*'`) y detener **ese**.
- **El watchdog reinicia el monitor solo** (se vio un `Backup de sesión RNF-01` nuevo a mitad de
  sesión sin que nadie relanzara). Útil de saber al leer logs largos.

---

## 6. Estado del código

Todo lo de esta sesión está commiteado. **Cero escrituras a la DB** en las 1h30 de QA.

| Archivo | Cambio |
|---|---|
| `app/core/monitor.py` | máscara del centro del hexágono; contador de resets + stalls nuevos; veto del ancla por botón; `_refresh_action_button` movido dentro de `_assign_s17_pj` |
| `app/tests/unit/test_monitor_trabe_mudo.py` | **nuevo** (7) — el handler no puede quedarse mudo |
| `app/tests/unit/test_monitor_equipado.py` | +4 del veto del ancla; gate actualizado |

---

## 7. Pendiente para la próxima

1. **Arreglar el gate del botón** (§4) → cierra el caso A.
2. **Caso C** — abrir un libre y volver sin equipar → abstención sin toast.
3. **Caso D** — reemplazo entre PJs (S23) → debe salir REEMPLAZADO, no "AHORA EN".
4. **Dedup ciego al dueño**: un disco visto libre y después equipado no se re-emite, así que en una
   sesión con escritura se quedaría **sin dueño en la DB para siempre**. Lo notó Daniel al preguntar
   por qué no lo re-detectaba. Arreglo: que la clave del dedup incluya al dueño.
5. **Sacar F8** — removal aprobado por Daniel (toca 7 lugares, incluido un botón visible del panel).
