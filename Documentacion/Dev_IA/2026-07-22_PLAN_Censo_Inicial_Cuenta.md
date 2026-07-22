# PLAN — Censo inicial de la cuenta (primer arranque del sistema)

**Fecha:** 2026-07-22
**Estado:** 📋 PLANIFICADO — sin implementar.
**Pedido de Daniel:**

> "esto sera lo primero que realizara el sistema al abrirse por primera vez que sera sincronizar los
> discos, roster y armas de la cuenta del usuario y esto se realizara con las capturas de extraccion
> que realiza el sistema tendra que ver los pj que tiene cuantos discos tiene cuantas armas etc"

**Depende de:** [SPEC Invariante equipado/asignado](./2026-07-22_SPEC_Invariante_Equipado_Asignado.md)
· **Habilita:** que cualquier escritura futura a la DB opere sobre un mapa que refleja la cuenta real.

---

## 1. Por qué esto va primero

La DB de hoy (49 agentes, 367 discos, 50 armas) es una **transcripción manual**. Nunca fue
verificada contra el juego, y ya diverge: el QA del 2026-07-20 encontró la DB diciendo "Jane" donde
el juego decía "Velina". Cada feature que escribe hereda ese error.

El censo invierte la relación: la cuenta es la verdad, la DB es su reflejo. Sin esto, todo lo que
construyamos encima está corrigiendo un mapa equivocado.

---

## 2. La restricción que define la arquitectura

**RNF-03 (ToS HoYoverse): el sistema NO puede navegar el juego.** Nada de simular clicks ni
automatizar. Solo mirar píxeles.

Consecuencia directa e ineludible: **el censo no es un proceso que el sistema ejecuta, es un
recorrido que el usuario hace y el sistema observa.**

Eso lo convierte en un **asistente guiado**: la app le dice a Daniel qué abrir, mira, tilda lo que
vio, y le muestra qué falta. El diseño se parece más a una checklist con acuse de recibo visual que
a un ETL.

**Corolario de diseño:** la pieza más importante del censo no es el parser — esos ya existen — sino
la **contabilidad de cobertura**. Un censo que no sabe qué NO vio es peor que no tener censo,
porque produce una foto parcial con cara de completa.

---

## 3. El problema central: cobertura

Todo parser puede fallar en silencio (un frame borroso, un scroll rápido, una animación). Entonces
el censo necesita responder en todo momento, **por entidad**:

| Estado | Significado |
|---|---|
| ✅ **VISTO** | observado con confianza suficiente en esta pasada |
| ⬜ **PENDIENTE** | el recorrido todavía no pasó por ahí |
| ⚠️ **DUDOSO** | se vio pero con confianza baja o datos incompletos → pedir repetición |
| ❓ **HUÉRFANO** | está en la DB y el censo NO lo encontró |

Los **huérfanos** son la categoría delicada. **No se borran.** Ausencia de evidencia no es evidencia
de ausencia (RNF-02): puede que el usuario no haya llegado a esa pantalla. Se listan en un reporte y
Daniel arbitra.

---

## 4. Los tres censos

### 4.1 Roster (PJs) — el más barato, casi listo

**Pantalla:** S15 (menú de personajes). Ya detectada, y ya hace OCR del nombre abajo a la izquierda
(commit `6d147d4`, ver memoria `project_menu_personajes_recon`).

**Recorrido:** el usuario scrollea la lista completa de personajes.

**Qué se extrae:** nombre → match contra `agents`. Opcionalmente Mindscape y nivel si están
legibles en el tile.

**Qué falta:** acumulador de nombres vistos + detección de fin de lista (¿el scroll llegó al final?).
Sin eso no se puede distinguir "no tiene ese PJ" de "no scrolleó hasta ahí".

**Salida:** PJs en el juego que no están en la DB (→ disparan
[Onboarding_Nuevo_PJ.md](../Onboarding_Nuevo_PJ.md)) y PJs en la DB que no aparecieron (→ huérfanos).

---

### 4.2 Discos — el más pesado, con la mejor ruta ya identificada

**Dos rutas posibles:**

| Ruta | Costo | Cobertura |
|---|---|---|
| **A. Por PJ** (S8 → S17 slot a slot) | 49 PJs × 6 slots ≈ **294 aperturas** | solo equipados (292) |
| **B. Inventario global** (S9, una pasada de scroll) | **1 pasada** | equipados **y** libres (367) |

**Recomendación: B como columna vertebral, A como repesca.** Ya está anotado como estrategia en la
memoria `project_inventario_global_badges`: una pasada del inventario global expone todos los badges
de dueño de una vez. Cubre los 75 libres, que la ruta A no ve nunca.

**Estado del código:** el parser S9 tiene el **núcleo hecho y testeado** (commit `23d7bbe`).
Pendiente según memoria `project_s9_inventario_captura`: dueño-por-badge, handler en el monitor, y
sync. El matcher de badges reusable ya existe (`owner_vote.py` / `badge_surface.py`, Fase 5R).

**El problema difícil de la ruta B — deduplicación en el scroll.** El mismo disco aparece en varios
frames mientras se scrollea. Hay que reconocer "este es el mismo que ya conté" sin contar de menos
(scroll rápido) ni de más. La identidad disponible es (set, slot, nivel, main, {substat+rolls}) — que
**no distingue discos gemelos**. Dos discos idénticos por firma son un solo registro para el sistema.

**Esto necesita diseño propio y probablemente una prueba de concepto antes de comprometerse.** Es el
riesgo técnico principal de todo el censo.

**Recomendación:** para el censo, usar posición en la grilla + continuidad entre frames como
desempate, no solo la firma. Un disco que aparece dos veces en la misma celda entre frames
consecutivos es el mismo; dos celdas distintas con la misma firma son dos discos.

---

### 4.3 Armas (W-Engines) — arranca de cero

**⚠️ No existe pantalla capturada.** Hay 20 carpetas de triggers para discos y **ninguna** para
W-Engines. Los 53 `weapons` del catálogo y los 50 `inventory_weapons` (40 asignados) son carga
manual sin verificar.

**Trabajo previo obligatorio** (mismo flujo que se usó para cada pantalla de discos):
1. Daniel captura screenshots del inventario de W-Engines → nueva carpeta
   `Documentacion/Screenshots_Triggers/Armas_Triggers/`.
2. Definir template + estado nuevo (`S24`+) en `detector.py` con su umbral y sus transiciones legales.
3. Escribir `parser_weapons.py`: nombre, nivel, refinamiento (P1-P5 en el español del juego), y dueño
   si el tile lo muestra.

**Ojo — `inventory_weapons` tiene el mismo par `equipado` / `agente_asignado` que `inventory_discs`.**
El invariante de la SPEC debe aplicarse **a las dos tablas**, no solo a discos. No lo habíamos
notado.

---

## 5. Reconciliación — qué hace el sistema con lo que ve

El censo **no sobrescribe a ciegas**. Clasifica y reporta:

| Caso | Acción |
|---|---|
| En juego y en DB, iguales | nada |
| En juego y en DB, **difieren** (dueño, nivel, refinamiento) | **el juego gana** — se corrige la DB, se loguea el cambio |
| En juego, **no** en DB | alta |
| En DB, **no** visto | **huérfano** → NO se borra, se lista para arbitraje |

**Regla dura (RNF-02):** el censo solo escribe lo que **observó con confianza**. Un parseo dudoso no
corrige nada — marca ⚠️ y pide repetir la pasada.

### El censo es el momento natural para establecer el invariante

Al terminar una pasada **completa** de discos, el sistema sabe exactamente qué disco está en cada
slot de cada PJ. Todo lo demás está libre. Ahí, y solo ahí, se puede afirmar
`(equipado=0, agente_asignado=NULL)` sobre el resto **por observación** en vez de por deducción.

Es decir: **el censo no requiere que el invariante ya esté implementado — el censo es lo que lo
establece.** La R2 de la SPEC pasa a ser el mecanismo que lo *mantiene* después.

Esto invierte el orden que habíamos supuesto ayer (primero invariante, después censo). Va al revés.

---

## 6. Fases propuestas

| # | Fase | Entregable | Depende de |
|---|---|---|---|
| **0** | **Contabilidad de cobertura** — modelo VISTO/PENDIENTE/DUDOSO/HUÉRFANO + tabla de sesión de censo + reporte | el esqueleto que las 3 fases siguientes llenan | — |
| **1** | **Censo de roster** (S15) | acumulador + fin de lista + reporte de altas/huérfanos | 0 |
| **2** | **Censo de discos** (S9) | dedup del scroll + dueño-por-badge + handler + sync | 0, PoC de dedup |
| **3** | **Censo de armas** | captura de triggers + estado nuevo + parser + sync | 0, screenshots de Daniel |
| **4** | **Reconciliación y cierre** | aplicar diferencias bajo RNF-01 + establecer el invariante + reporte final en `audit/` | 1, 2, 3 |
| **5** | **UI del asistente** | checklist en vivo: qué falta, qué se vio, cuándo está completo | 0-4 |

**Fase 0 primero, sin excepción.** Es lo que hace que las otras sean verificables.

**Sugerencia de arranque:** fases 0 + 1 juntas. El roster es chico (49 filas), la pantalla ya está
detectada y ya OCRea el nombre — sirve de banco de pruebas barato para el modelo de cobertura antes
de meterse con el scroll de 367 discos.

---

## 7. Decisiones abiertas (para Daniel)

1. **¿El censo es obligatorio en el primer arranque, o se puede postergar?** Un asistente que
   bloquea la app hasta terminar 3 recorridos completos es hostil. Alternativa: modo degradado
   (display-only) hasta que el censo esté completo, con recordatorio.
2. **¿Se puede hacer en varias sesiones?** Implica persistir el progreso del censo entre arranques
   (una tabla `census_runs` + estado por entidad). Recomendación: sí — un censo de 367 discos en una
   sentada es mucho pedir.
3. **¿Qué pasa con los huérfanos al cerrar el censo?** Opciones: dejarlos como están; marcarlos
   `notas='no_visto_en_censo_<fecha>'`; o pedir confirmación uno por uno. Recomendación: la segunda
   — deja rastro sin destruir nada.
4. **¿El censo re-corre periódicamente?** Después de cada patch la cuenta cambia. Podría reusarse
   como "auditoría de sincronía" en vez de ser solo de primer arranque.

---

## 8. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Dedup del scroll de discos** (§4.2) | alto — es el corazón de la fase 2 | PoC antes de comprometerse; posición en grilla como desempate |
| **Discos gemelos indistinguibles por firma** | medio — conteo erróneo | aceptar y reportar como ambigüedad explícita, no resolver a la fuerza (RNF-02) |
| **Censo parcial que parece completo** | alto — corrompe todo lo que venga después | la fase 0 existe exactamente para esto |
| **RNF-06 durante el scroll** | medio — parsear cada frame de una pasada larga es caro | reusar el gate de foco y el polling adaptativo ya existentes |
| **Fuga de memoria en pasadas largas** | medio | ya hubo una (RNF-06, commit `0863319`); vigilar con el watchdog existente |

---

## 9. Lo que este plan NO cubre

- Cómo se re-sincroniza la DB **hoy**, antes de que el censo exista. Si hace falta antes, es un
  saneamiento manual puntual, no este sistema.
- Mindscapes, niveles de habilidad, Awakening/Silueta Potencial. El pedido dice "discos, roster y
  armas". El perfil del agente (S18/S19) ya tiene parser propio (`parser_agent_stats.py`) y podría
  sumarse después como cuarto censo.
