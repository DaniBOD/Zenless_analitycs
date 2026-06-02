# Auditoría — Corrección de rol/elemento en `agents`

**Fecha:** 2026-06-01
**Migración:** `db/migrations/2026-06-01_07_fix_roles_elementos.sql`
**Operador:** Claude Code (Opus 4.8) · solicitado por DaniBOD
**RNF aplicadas:** RNF-01 (backup + transacción + PRAGMA), RNF-02 (verificación contra fuentes autorizadas, sin inventar)

---

## 1. Contexto

Durante el QA en vivo del **2026-05-31** (Hito 2.8, parser S18 con PaddleOCR), el parser
`app/core/parser_agent_stats.py` empezó a leer rol/elemento desde la **PANTALLA del juego**
(ground truth, autoritativo — RF §6.5). Al comparar contra la DB se detectaron agentes con
`rol`/`elemento` mal seedeados. El scoring/recomendador (RF-04/06) lee rol/elemento **de la
DB**, así que esta data degradaba las recomendaciones (Equipar/Mejorar/Reserva/Descartar).

Daniel flaggeó 4 agentes (Ju Fufu, Yuzuha, Dialyn, Yixuan). La auditoría:
1. Confirmó los 4 contra fuentes autorizadas.
2. **Escaneó los 46 agentes** y encontró **3 errores adicionales** (Pulchra, Lucía, Ye Shunguang).
3. Confirmó "Tinta áurica" (Auric Ink) como elemento nuevo legítimo de v2.0.

---

## 2. Metodología de verificación (RNF-02)

- **Fuente primaria:** pantalla S18 del juego (ground truth para los 4 flaggeados por Daniel).
- **Fuentes de corroboración / scan:** Prydwen.gg, Game8.co, ZZZ Fandom Wiki.
- **Validación interna:** la tabla `pj_weapon_synergy` es un *template determinista por rol*
  (BONUS_MATRIX). Se cruzó la firma de synergy de cada agente contra su columna `rol`:
  el único mismatch interno fue Nangong Yu (ver §5). Los 6 errores reales tenían synergy
  **consistente con su rol erróneo** (seedeados mal de raíz), por eso no los detectó el cruce
  interno y requirieron verificación externa.

---

## 3. Cambios aplicados

### 3.1 Roles corregidos (6 agentes)

| id | Agente | rol DB (antes) | rol correcto | Atributo/Especialidad real (fuente) |
|----|--------|----------------|--------------|--------------------------------------|
| 11 | Pulchra | Ataque | **Aturdimiento** | Physical **Stun** (Prydwen/Game8/Fandom) |
| 22 | Lucía | Defensa | **Soporte** | Ether **Support**, HP-scaling (Game8/Prydwen/Fandom) |
| 23 | Ye Shunguang | Disruptivos | **Ataque** | Honed Edge (≈Físico) **Attack** (Game8/Prydwen/Fandom) |
| 24 | Yuzuha | Anomalía | **Soporte** | Physical **Support** (pantalla S18 + Game8/Prydwen) |
| 27 | Dialyn | Ataque | **Aturdimiento** | Physical **Stun** (pantalla S18 + Game8/Prydwen/Fandom) |
| 29 | Ju Fufu | Soporte | **Aturdimiento** | Fire **Stun** (pantalla S18 + Game8/Prydwen) |

### 3.2 Elemento corregido (1 agente)

| id | Agente | elemento DB (antes) | elemento correcto | Fuente |
|----|--------|---------------------|-------------------|--------|
| 31 | Yixuan | Éter | **Tinta áurica** (Auric Ink) | pantalla S18 + Fandom (atributo único v2.0, ≡Éter p/modificadores) |

> Yixuan: el **rol** `Disruptivos` (Rupture) ya era **correcto** — solo cambió el elemento.

### 3.3 Remap de `pj_weapon_synergy` (36 filas)

La synergy se sembró con la matriz del rol **erróneo** en los 6 agentes con rol corregido.
Se remapeó copiando la matriz canónica (BONUS_MATRIX) del rol destino desde un agente de
referencia, marcando la procedencia en `razon` (`[remap rol 2026-06-01]`; `fuente='manual'`
por CHECK `fuente IN ('manual','ai_claude')`):

| Rol destino | Ref (matriz canónica) | Agentes remapeados |
|-------------|------------------------|---------------------|
| Aturdimiento | Lycaon (id 3) | Pulchra (11), Dialyn (27), Ju Fufu (29) |
| Soporte | Lucy (id 9) | Lucía (22), Yuzuha (24) |
| Ataque | N.º 11 (id 6) | Ye Shunguang (23) |

Total `pj_weapon_synergy` se mantiene en **276** filas (6×6 borradas, 6×6 reinsertadas).

### 3.4 `agent_thresholds` — revisado, SIN cambios (RNF-02)

| id | Agente | thresholds actuales | ¿Acorde al rol corregido? |
|----|--------|---------------------|----------------------------|
| 11 | Pulchra | impacto, prob_critico, ataque | ✅ Sí (impacto = stat clave de Stun) |
| 22 | Lucía | pv | ✅ Sí (Support HP-scaling) |
| 23 | Ye Shunguang | prob_critico, dano_critico, tasa_perforacion | ✅ Sí (perfil Attack/crit) |
| 24 | Yuzuha | maestria_anomalia, ataque, rec_energia | ⚠️ Dudoso para Soporte → **FLAG re-derivar** |
| 27 | Dialyn | prob_critico, dano_critico | ⚠️ Stun sin `impacto` → **FLAG re-derivar** |
| 29 | Ju Fufu | ataque, prob_critico, rec_energia | ⚠️ Stun sin `impacto` → **FLAG re-derivar** |

No se inventaron thresholds (RNF-02). Los 3 ⚠️ quedan para re-derivar contra Prydwen en su
próximo QA. Los thresholds de Pulchra/Lucía/Ye Shunguang ya estaban correctos para su rol
real (otra señal de que el error fue solo en la columna `rol`, no en el perfil de stats).

---

## 4. RNF-01 — Integridad

- **Backup previo:** `db/danibod_zzz_v2.backup_premig_20260601_201813.db` (gitignored).
- **Transacción:** `BEGIN TRANSACTION; … COMMIT;` (ejecutada vía `executescript`).
- **`PRAGMA foreign_key_check`:** OK (sin filas).
- **`PRAGMA integrity_check`:** `ok`.
- **Smoke checks (todos pasan):**
  - roles corregidos = 6 (esperado 6)
  - Yixuan elemento='Tinta áurica' = 1 (esperado 1)
  - filas synergy remapeadas = 36 (esperado 36)
  - synergy Ju Fufu ≡ Lycaon / Yuzuha ≡ Lucy / Ye Shunguang ≡ N.º 11 → diff 0
  - total `pj_weapon_synergy` = 276

---

## 5. Hallazgos pendientes de decisión (NO modificados — RNF-02)

1. **Nangong Yu (id 26) — synergy hybrid.** `rol='Aturdimiento'` y `elemento='Éter'` son
   **correctos** (Ether Stun, verificado). Pero su `pj_weapon_synergy` usa la matriz de
   **Anomalía** (anomaly_proficiency 1.5), no la de Aturdimiento. Game8 lo describe como
   *Stun/Anomaly hybrid* que escala Daze con Maestría de Anomalía → puede ser **intencional**.
   **Decisión DaniBOD:** ¿dejar la matriz Anomalía (hybrid) o normalizar a Aturdimiento?

2. **Ye Shunguang (id 23) — atributo único "Honed Edge".** Su atributo real es *Honed Edge*
   (único, ≈Físico para modificadores), análogo a Auric Ink de Yixuan. Sin nombre ES capturado
   de pantalla, se conserva `elemento='Físico'` + nota tentativa en `agents.notas`
   (`pending_screen_ES_name`). **Pendiente:** capturar su pantalla S18 para confirmar el nombre ES.

3. **Thresholds Ju Fufu / Yuzuha / Dialyn** — re-derivar contra Prydwen (ver §3.4).

4. **Sporos (id 28)** — la DB lo llama "Sporos"; las fuentes EN lo llaman "Seed" (Obol Squad,
   Electric Attack). rol/elemento `Eléctrico/Ataque` coinciden ✅. Posible diferencia de
   localización del nombre — no es error de rol/elemento, solo se anota.

---

## 6. Agentes verificados como CORRECTOS (sin cambios)

Verificados explícitamente contra fuentes externas: Nangong Yu (Ether Stun), Manato (Fire
Rupture=Disruptivos), Seth (Electric Defense), Sunna (Physical Support), Zhao (Ice Defense),
Pan Yinhu (Physical Defense), Orphie & Magus (Fire Attack), Sporos/Seed (Electric Attack).

Los 31 restantes del roster de lanzamiento (1.x) se asumen correctos (alta confianza, sin
mismatch interno synergy↔rol). Si se quiere certeza total, se pueden re-verificar en un pase
posterior.

---

## 7. Decisiones de DaniBOD y mig 08 (2026-06-01)

Tras revisar los flags de §5, DaniBOD resolvió (aplicado en
`db/migrations/2026-06-01_08_elemento_estandar_y_thresholds.sql`):

1. **Nangong Yu (26):** es 100% Stunner con subrol oculto sub-anómalo →
   `rol='Aturdimiento'` se mantiene (correcto). Su synergy/thresholds
   anomaly-flavored son **intencionales** (su Daze escala con Maestría de
   Anomalía) → **NO se normaliza** (forzar la matriz vanilla degradaría el
   scoring de sus armas de AM).

2. **Política de elementos — equivalente estándar:** los atributos "especiales"
   se guardan como su elemento estándar equivalente (heredan modificadores):
   - **Yixuan**: `Tinta áurica` → **`Éter`** (REVERTIDO respecto a mig 07).
   - **Ye Shunguang**: Honed Edge → `Físico` (sin cambio).
   - **Miyabi**: Frost/Escarcha → `Hielo` (ya estaba).
   Se **retira `Tinta áurica`** del dominio. Se **incorpora `Viento`** (Wind) como
   elemento estándar nuevo (proactivo, sin agentes aún) en el parser
   (`_ELEMENTOS_DB`, `_ELEMENTO_SCREEN_MAP`), modelo relacional y project-context.
   Distribución final: Físico 13 · Eléctrico 12 · Fuego 9 · Éter 7 · Hielo 5.

3. **Thresholds re-derivados (Prydwen/Game8, RNF-02):**
   - **Ju Fufu (29)**: `prob_critico` 60/70 → **50/60** ("CRIT Rate ≥50% para 4P
     King"); ataque (3000/3400) y rec_energia (1.8/2.2) se mantienen.
   - **Dialyn (27)**: **+`rec_energia` 1.5/2.0** ("ER acelera EX → más Daze");
     prob_critico (70/90) y dano_critico (80/120) se mantienen.
   - **Yuzuha (24)**: `ataque` → **3000/3200** ("≥3000 ATK"); `maestria_anomalia`
     120/180 → **180/220** ("~200 AM para tope de buffs"); `rec_energia` óptimo
     2.0 → **2.2**.

**RNF-01 mig 08:** backup `db/...backup_premig_20260601_203241.db` · transacción ·
`foreign_key_check` OK · `integrity_check` ok · 6 smoke checks ✓.

---

*Generado por Claude Code siguiendo RNF-01/02 · DaniBOD ZZZ Analytics.*
