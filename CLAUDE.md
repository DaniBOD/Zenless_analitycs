# CLAUDE.md — DaniBOD ZZZ Analytics

> **Para vos, Claude Code.** Esta es tu hoja de ruta cuando arrancás sesión nueva en este repo. La planificación ya está cerrada en docs canónicos; tu trabajo es **implementar** siguiendo el roadmap, **no** revisar diseño salvo que un hallazgo lo justifique.
>
> **Última actualización:** 2026-05-04
> **Owner:** Daniel (DaniBOD · UID 1000860143)
> **Stack:** Python 3.11+ · SQLite · PySide6 · OpenCV · Tesseract · PaddleOCR · Anthropic SDK · Claude Code (vos)

---

## 0. Lectura de contexto — antes de tocar nada

En este orden, leé estos 4 archivos:

0. **[`Documentacion/Dev_IA/00_Practicas_Aprendidas.md`](./Documentacion/Dev_IA/00_Practicas_Aprendidas.md)** — **empezá por acá.** No es teoría: cada regla salió de un error concreto de este proyecto, y varias se repitieron disfrazadas de problemas distintos. Los titulares, para que no haya excusa de no haberlo abierto:

   | | |
   |---|---|
   | **A1** | Medir antes de afirmar. Un número heredado **no** es una medición. |
   | **A2** | El silencio no es un aprobado — puede ser que ese código nunca corrió. |
   | **A3** | Verificar el **efecto**, no la intención. Rompé el test a propósito. |
   | **A4** | Verificar el estado, no deducirlo (los folders no nombran el estado). |
   | **A5** | Un recorte de la evidencia es otra evidencia. `grep -c` antes de concluir. |
   | **B1** | Una sola autoridad por pregunta. Dos definiciones de lo mismo es una de más. |
   | **B2** | Abstenerse no debe costar el dato entero. Y no borres por ausencia. |
   | **B3** | Un audit no muta su objeto de estudio (`prune=False`, sha256 antes/después). |
   | **C1** | Medí contra un baseline validado, antes y después. No inventes métricas. |
   | **C2** | Un reloj declara una unidad, no una granularidad. Un sello no es un ID. |
   | **D1** | Todo lo que la app lee vive **dentro de `app/`** (si no, muere empaquetado). |
   | **D2** | Una red que en dev nunca se ejerce, nunca se testea. |
   | **E1** | Una investigación sin archivo no se puede revisar ni retomar. |
   | **E3** | Un cambio por vez, y el diagnóstico primero. |

1. **[`project-context-IA.md`](./project-context-IA.md)** (~300 líneas) — snapshot maestro. Estado de la DB, RFs, decisiones cerradas, glosario. Es el archivo *autoritativo*.
2. **[`Documentacion/Roadmap_Implementacion/Roadmap_Motor_Captura_Scoring.md`](./Documentacion/Roadmap_Implementacion/Roadmap_Motor_Captura_Scoring.md)** — Fase 2 (motor de captura + scoring). Define los 7 sub-fases con criterios de aceptación duros por hito. **Esta es tu hoja de ruta**.
3. **Cuando llegues al hito que toca, leé el RF correspondiente** (`Documentacion/RF_*/RF-Logic_*.md`). Si hay discrepancia entre código y RF, manda el RF.

El `README.md` de la raíz es la **portada del repositorio** (para humanos que llegan de GitHub), no una fuente para vos: no tiene detalle operativo. La referencia profunda de la Fase 1 —las 1214 líneas que antes estaban ahí— quedó archivada en [`Documentacion/README_Referencia_Fase1_2026-05.md`](./Documentacion/README_Referencia_Fase1_2026-05.md); consultala sólo por un detalle puntual, y recordá que su §2 y §12 están desactualizadas.

---

## 1. Identidad del proyecto (TL;DR)

Sistema de análisis y optimización de cuenta para Zenless Zone Zero. **Standalone Windows** (`.exe` PySide6, no web). Único usuario: DaniBOD. La app monitorea el cliente del juego, captura discos farmeados con OCR, los puntúa contra el roster de 45 PJs (46 post-onboarding Cissia) y emite recomendaciones (Equipar / Mejorar / Reserva / Descartar) en tiempo real con latencia objetivo < 500 ms.

**Tres superficies:**
- **Tray icon** — ícono permanente en system tray.
- **Toast flotante** 380×116 px, esquina inferior derecha, always-on-top.
- **Panel principal** 1320×820 px, 9 pestañas (Captura en vivo, Histórico, Roster, Discos, Equipos, Lategame, Armas, Catálogos, Configuración).

**Estado actual (2026-05-04):**
- ✅ DB completa (31 tablas, 5 migraciones aplicadas, 332 discos, 45 PJs, 6 arquetipos).
- ✅ Diseño cerrado para todos los RF (RF-04/05/06/09/11/12/13/14).
- ✅ Mockups de UI generados con Claude Design para 5 pantallas (toasts, panel LIVE, panel DISCOS, modal disco, modal PJ con paleta dinámica).
- ✅ Roadmap Fase 2 redactado.
- 🟡 Onboarding Cissia (PJ nuevo v2.7) en SQL listo, pendiente ejecutar.
- ❌ Cero código del `.exe` implementado todavía. **Vos arrancás acá**.

---

## 2. Reglas no negociables (RNF) — aplican a TODA tarea

| ID | Regla | Cómo se hace cumplir |
|----|-------|----------------------|
| **RNF-01** | **ETL sin fallas** — toda manipulación de DB con backup previo + transacción + `PRAGMA foreign_key_check` + `PRAGMA integrity_check`. | Antes de cualquier `INSERT/UPDATE/DELETE/ALTER` o aplicar migración: copiar `db/danibod_zzz_v2.db` a `db/danibod_zzz_v2.backup_premig_<TIMESTAMP>.db`. SQL dentro de `BEGIN TRANSACTION; … COMMIT;`. Después: `PRAGMA foreign_key_check; PRAGMA integrity_check;`. Loggear todo en `audit/`. |
| **RNF-02** | **Análisis minucioso** — cero shortcuts. Dato no confirmado ⇒ NULL + flag tentativo. | Fuentes autorizadas para validar: Prydwen.gg, HoYoLAB, Game8, IcyVeins, 141store, Fandom oficial. **No inventar** stats, thresholds, sinergias. Si Prydwen no lo dice y HoYoLAB tampoco, dejar NULL con `notas='pending_capture'` o `fuente='tentativo'`. |
| **RNF-03** | **Compatibilidad ToS HoYoverse** — solo pixels en pantalla. | NUNCA usar `pymem`, lectura de memoria, inyección de DLL, `keyboard.send()`, simulación de inputs, automatización de gameplay. Solo `mss`/`win32` para captura de imagen + OCR + `pynput.keyboard.Listener` (lectura, no envío). Equivalente legal a Inventory Kamera (Genshin). |
| **RNF-06** | **Responsividad** — toast < 500 ms, optimizador discos < 500 ms, lookup RF-12 < 50 ms, recálculo tier list < 3 s, RAM idle < 200 MB, CPU polling < 3 %. | Cada función crítica con `pytest-benchmark`. Decorator `@measure_latency` registra en tabla `metrics_latency` (ver `Documentacion/QA/QA-06_Performance_y_UX.md`). |

---

## 3. Convenciones operativas — pegate a esto siempre

### 3.1 Antes de cualquier write a DB

```bash
# Backup obligatorio (PowerShell)
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item db\danibod_zzz_v2.db db\danibod_zzz_v2.backup_premig_$ts.db
```

Backups runtime están **gitignoreados** (`db/danibod_zzz_v2.backup_*.db`). Si querés persistir uno como snapshot intencional, copiarlo a `audit/` (esa carpeta sí se versiona).

### 3.2 Estructura de docs canónicos

| Carpeta | Contenido | Cuándo consultar |
|---------|-----------|------------------|
| `Documentacion/RF_Captura_Discos/` | RF-04 (sync captura) + RF-05 (sync upgrade) + RF-09 (OCR híbrido) | Antes de tocar `app/core/{monitor,detector,parser_disc,sync_*,ocr_*}.py` |
| `Documentacion/RF_Optimizador/` | RF-06 (optimizador build greedy + bonus pass) | Antes de `app/core/optimizer.py` |
| `Documentacion/RF_Optimizador_Equipos/` | RF-12 (sinergias IA + lookup determinista) | Fase 3 |
| `Documentacion/RF_Lategame_Validation/` | RF-13 (lategame F11 + tier list bayesiana) | Fase 4 |
| `Documentacion/RF_Optimizador_Armas/` | RF-14 (W-Engines scoring contextual) | Fase 5 |
| `Documentacion/QA/` | Plan maestro + 7 sub-docs (ETL, scoring, OCR, IA, lategame, performance, regresión por patches) | Antes de cerrar cualquier hito (verificar cobertura mínima) |
| `Documentacion/Modelo_Relacional/` | Schema canónico + diagrama ER | Antes de proponer nueva tabla o columna |
| `Documentacion/Onboarding_Nuevo_PJ.md` | 8 pasos canónicos para agregar PJ nuevo | Cada vez que sale un patch (~6 sem) |
| `Documentacion/Onboarding_Nuevos_Assets.md` | W-Engines / Sets / Facciones | Cuando sale un set/arma nueva |
| `Documentacion/Roadmap_Implementacion/` | Roadmap Fase 2 (este es tu mapa de implementación) | **Siempre** |
| `Documentacion/Interfaz/` | Brief de diseño + mockups + assets visuales | Cuando llegues a Fase 3 (RF-11 UI) |

### 3.3 Layout previsto de `app/`

Cuando lo crees (Fase 2.1), respetá este layout:

```
app/
├── __init__.py
├── main.py
├── config/{defaults,user_config}.toml
├── core/
│   ├── stats_vocab.py     ← Hito 2.0.2 (canon de nombres + parser)
│   ├── scoring.py         ← Hito 2.2 (engine puro)
│   ├── score_normalizer.py
│   ├── recommender.py     ← Hito 2.2.3 (decisión 4-vías)
│   ├── ocr_backend.py     ← Hito 2.4.1 (interfaz abstracta)
│   ├── ocr_tesseract.py
│   ├── ocr_paddle.py
│   ├── capturer.py        ← Hito 2.4.5 (mss + crop)
│   ├── detector.py        ← Hito 2.4.4 (estado pantalla)
│   ├── parser_disc.py     ← Hito 2.4.6
│   ├── monitor.py         ← Hito 2.4.7 (polling adaptativo)
│   ├── sync_equip.py      ← Hito 2.5.1
│   ├── sync_upgrade.py    ← Hito 2.5.2
│   └── optimizer.py       ← Hito 2.6.2 (greedy + bonus pass)
├── db/{connection,repositories}.py
├── scripts/
│   ├── audit_inventory_discs.py        ← Hito 2.0.1 ⭐ TU PRIMER CÓDIGO
│   ├── restandarize_inventory_discs.py ← Hito 2.0.4
│   ├── seed_substat_preferences.py     ← Hito 2.0.5
│   └── score_existing_inventory.py     ← Hito 2.3
├── resources/{templates,icon.ico}
└── tests/{unit,integration,regressions,fixtures}/
```

Detalle exacto en Roadmap §3.

### 3.4 Workflow de git por hito

```bash
git checkout -b feature/<nombre-hito>     # desde main
# ... hacer el trabajo ...
# backup DB si tocás migrations / scripts ETL
# tests verdes
git add .
git commit -m "feat(<scope>): <descripción> · cierra Hito 2.X.Y"
git tag phase-2.X-<nombre>                # solo al cerrar fase completa
git push origin feature/<nombre-hito>
# PR → merge a main
```

### 3.5 Después de cerrar un hito

1. Actualizar `project-context-IA.md` §3 (counts) y §4 (estado del RF).
2. Si tocaste schema: actualizar `Documentacion/Modelo_Relacional/README.md`.
3. Si cargaste data nueva: dejar reporte en `audit/`.
4. Tag git solo cuando cierres una **fase completa** (no por hito).

---

## 4. Tareas inmediatas — en este orden

> **Las primeras dos (T0 y T1)** son trabajo operativo que el sandbox de Cowork no pudo hacer por restricción de filesystem (no permitía borrar archivos / hacer push). Vos las podés terminar nativo en Windows con bash/PowerShell completos. **Hacelas antes de empezar a codear**.

### T0 — Inicializar repo git + primer push (5 min)

**Contexto:** Cowork dejó listo `.gitignore` + un script `tools\init_repo.ps1` + el `.git/` parcial corrupto (que el script limpia).

**Dos opciones:**

**Opción A — usar el script tal cual** (recomendada si estás en PowerShell):
```powershell
cd D:\Proyectos\Zenless_analitycs
powershell -ExecutionPolicy Bypass -File tools\init_repo.ps1
```
El script: limpia `.git/` corrupto, hace `git init -b main`, configura user, agrega remote a `https://github.com/DaniBOD/Zenless_analitycs.git`, detecta si el repo remoto está vacío (caso A) o con commits previos (caso B), y procede en consecuencia.

**Opción B — hacerlo manualmente** (si querés control fino o el script falla):
```powershell
cd D:\Proyectos\Zenless_analitycs
Remove-Item .git -Recurse -Force      # limpiar .git/ corrupto del sandbox
git init -b main
git config user.email "daniel.pilquil.003@gmail.com"
git config user.name "DaniBOD"
git config core.autocrlf true
git remote add origin https://github.com/DaniBOD/Zenless_analitycs.git

# Verificar si el remoto tiene commits
git ls-remote --heads origin
# Si vacío → seguir con add+commit+push -u
# Si tiene → fetch + checkout origin/main + integrar local + commit

git add .
git commit -m "chore: initial commit — Fase 1 cerrada + roadmap Fase 2 + onboarding Cissia pendiente

- DB v2 completa (31 tablas, 5 migraciones, 332 discos, 45 PJs, 6 arquetipos).
- Documentacion RF-04/05/06/09/11/12/13/14 cerrada.
- Brief de diseño + mockups Claude Design (sesión 1).
- Brief sesión 2 redactado (pantallas restantes UI).
- Roadmap Fase 2 (motor captura + scoring) redactado.
- Onboarding Cissia (v2.7, CRIT, variante Metropolitan Order Division) en SQL listo.

Refs: project-context-IA.md, Documentacion/Roadmap_Implementacion/Roadmap_Motor_Captura_Scoring.md"

git push -u origin main
```

**Aceptación:** `git status` clean, `git log` muestra el commit, GitHub muestra el repo poblado.

### T1 — Aplicar onboarding Cissia (10 min)

**Contexto:** SQL listo en `db/migrations_pendientes/2026-05-04_onboarding_cissia.sql`. Detalle completo en `audit/onboarding_cissia_20260504.md`.

**Lo que hace el SQL:**
1. INSERT en `agents` (Cissia · S · Eléctrico · Ataque · M0 · CRIT · v2.7).
2. INSERT 5 thresholds (perfil Crit-DPS Eléctrico).
3. INSERT score_thresholds defaults (0.75 / 0.50).
4. INSERT awakening placeholder (no desbloqueado en v2.7).
5. INSERT 6 filas en `pj_weapon_synergy` (BONUS_MATRIX rol Ataque).
6. UPDATE 4 discos sueltos (id 261, 263, 259, 268) → asignar a Cissia.
7. INSERT 2 discos nuevos (slot 4 Floración + slot 6 Nana).
8. PRAGMA + 8 smoke checks que muestran `expected_*` esperado.

**Pasos de ejecución:**

```powershell
cd D:\Proyectos\Zenless_analitycs

# 1. Backup obligatorio (RNF-01)
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item db\danibod_zzz_v2.db db\danibod_zzz_v2.backup_premig_$ts.db
Write-Host "Backup: db\danibod_zzz_v2.backup_premig_$ts.db"

# 2. Aplicar el SQL
sqlite3 db\danibod_zzz_v2.db ".read db/migrations_pendientes/2026-05-04_onboarding_cissia.sql"

# 3. Validar smoke checks visualmente: cada SELECT al final del SQL debe mostrar
#    una columna 'expected_N' con valor exactamente N. Si algún expected falla:
#    sqlite3 db\danibod_zzz_v2.db ".restore 'db/danibod_zzz_v2.backup_premig_$ts.db'"

# 4. Si todo OK, mover a migrations aplicadas
Move-Item db\migrations_pendientes\2026-05-04_onboarding_cissia.sql `
          db\migrations\2026-05-04_06_onboarding_cissia.sql
```

**Después de aplicar, actualizar `project-context-IA.md` §3 con los nuevos counts:**
- `agents`: 45 → **46**
- `inventory_discs`: 332 → **334**
- `agent_thresholds`: 103 → **108**
- `agent_score_thresholds`: 45 → **46**
- `agent_awakenings`: 5 → **6**
- `pj_weapon_synergy`: 270 → **276**

Hacer commit:
```powershell
git add db\danibod_zzz_v2.db db\migrations\2026-05-04_06_onboarding_cissia.sql audit\onboarding_cissia_20260504.md project-context-IA.md Documentacion\Interfaz\Facciones_Logos\
git commit -m "feat(roster): onboarding Cissia v2.7 (46/46 agentes) + 2 discos nuevos

- Agente Cissia (S · Eléctrico · Ataque · M0 · CRIT con variante MOD).
- W-Engine: Taladradora giratoria - Eje (A-rank R5).
- Build: 4pc Floración del alba + 2pc Nana a la luz cenicienta.
- 4 discos sueltos reasignados (slots 1, 2, 3, 5).
- 2 discos nuevos insertados (slot 4, slot 6).
- Logo nuevo: Faction_Metropolitan_Order_Division_Icon.webp + README facciones actualizado.
- Corrección histórica: Sporos != Cissia (eran PJs distintos)."
git push origin main
```

### T2 — Hito 2.0.1: `audit_inventory_discs.py` ⭐ tu primer código

**Especificación completa en Roadmap §2.0.1.** Resumen:

**Output esperado:** `audit/inventory_discs_audit_<YYYYMMDD>.md` con:
- Distribución de tipos por columna `val1-val4` (typeof) — esperamos confirmar el split ~149 TEXT / ~183 REAL detectado en la inspección preliminar (post-Cissia será 150/185 aprox).
- Inventario de strings únicos en `main_stat`, `sub1-4` con conteo, agrupado por canónico vs alias vs desconocido.
- Filas con valores fuera de rango: `rolls > 5`, `nivel > 15`, suma de rolls por disco > 5.
- FK rotas (set_id sin match en disc_sets, agente_asignado sin match en agents).
- Filas con `main_stat` no permitido por slot según RF-04 §7.2.1 (ver `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` §7.2.1 para tabla canónica).
- **Hallazgo conocido a confirmar:** discos `id=54` y `id=185` tienen main_stat='Tasa Anomalía 30%' en slot 6, lo cual es inválido (mains slot 6 no incluyen Tasa de Anomalía). Probable confusión OCR/transcripción con "Maestría de Anomalía". El audit los debe listar.

**Reglas:**
- **Read-only**. No tocar la DB en absoluto.
- Path DB: `db/danibod_zzz_v2.db` (asumir desde la raíz del repo).
- Loggear conteo total al inicio para que el usuario verifique que está leyendo la DB correcta.
- Output Markdown con headers, tablas y emoji-prefijos para errores (`⚠️`).

**Tests sugeridos** en `app/tests/unit/test_audit_inventory_discs.py`:
- Sobre fixture DB en memoria (con 3 discos artificiales: uno OK, uno con rolls=6, uno con main inválido para slot), verificar que el reporte detecta los 2 problemas.

**Aceptación:** reporte generado, revisado por el usuario, firmado en commit.

### T3+ — Seguir el roadmap

Después de cerrar T2, ir a Roadmap §2.0.2 (vocabulario canónico `app/core/stats_vocab.py`), después §2.0.3 (migración 06), etc. **No te saltees orden**: cada hito tiene aceptación que bloquea al siguiente.

---

## 5. Cómo decidir cuando algo no está claro

### Si encontrás algo que contradice el diseño

NO parchees el código para acomodarlo. **Abrí issue / discusión** y proponé:
1. Cuál doc RF debería actualizarse.
2. Qué cambia en el roadmap.
3. Si requiere migración de schema, cómo se hace sin perder data.

El roadmap §11 lista los rituales operativos para esto.

### Si una decisión técnica te queda 50/50

Convención del proyecto: **mandá la decisión más conservadora respecto a RNF-01/02** (no toques data si no estás seguro, dejá NULL antes que inventar, hacé backup extra).

### Si tenés que llamar API externa

- Anthropic API: respetar `cap_usd_mensual` (default $5/mes) en `app/config/user_config.toml::ai_catalog`. Usar prompt caching. Loggear cada llamada en `ai_catalog_runs`. Detalle en RF-12 §6.
- Prydwen / HoYoLAB / Game8: scrapers en `app/scripts/scrape_*.py`, idempotentes, con rate limit, snapshot a tabla `*_snapshots`. Detalle en docs RF correspondientes.

### Si hay un patch de ZZZ

Ejecutar `Documentacion/QA/QA-07_Regresion_Patches.md` paso a paso ANTES de tocar nada más. Cada patch trae 1-2 PJs nuevos (flujo `Onboarding_Nuevo_PJ.md` 8 pasos) + posibles W-Engines nuevos + posibles re-balanceos.

---

## 6. Lo que el sandbox de Cowork dejó listo y vos puede aprovechar

| Archivo | Qué es | Tu acción |
|---------|--------|-----------|
| `.gitignore` | Excluye `Inventario/` (200 MB), backups runtime, artifacts Python, IDE, configs personales | Usar tal cual |
| `tools/init_repo.ps1` | Script PowerShell que inicializa git completo (limpia .git corrupto, init, config, remote, push) | Ejecutar en T0 (o hacer los pasos a mano si preferís) |
| `tools/README_git_setup.md` | Doc del setup de git | Leer si dudás |
| `db/migrations_pendientes/2026-05-04_onboarding_cissia.sql` | SQL completo de onboarding Cissia con BONUS_MATRIX, 8 smoke checks, todo | Aplicar en T1 |
| `audit/onboarding_cissia_20260504.md` | Audit del onboarding (datos confirmados, decisiones de modelado, hallazgo Sporos≠Cissia) | Leer una vez antes de aplicar T1 |
| `Documentacion/Roadmap_Implementacion/Roadmap_Motor_Captura_Scoring.md` | Hoja de ruta completa de Fase 2 con 7 sub-fases y criterios de aceptación duros | **Tu mapa principal** |
| `Documentacion/Interfaz/claude_design_upload/BRIEF_SESION2_pantallas_restantes.md` | Brief para próxima sesión con Claude Design (pantallas pendientes UI) | Solo cuando llegues a Fase 3 |
| `Documentacion/Interfaz/mockups/Codigos-claude-desing/` | Código JSX + tokens.css de mockups generados por Claude Design (sesión 1) | Referencia visual cuando llegues a RF-11 |

---

## 7. Glosario rápido (vocabulario del dominio)

| Término | Significado |
|---------|-------------|
| **Disco** | Drive disc = artefacto/equipo. 6 slots, set 2pc/4pc, mainstat + 4 substats con `rolls` 0-5. |
| **W-Engine** | Arma. `refinamiento` 1-5 (P1-P5 en español del juego). |
| **Mindscape (M)** | Constelación 0-6. `M0` = base, `M6` = todos los nodos. |
| **Awakening / Despertar / Silueta Potencial** | Sistema v2.5+. Comprable en tienda. "Agotado" = nv6. "Límite ×N" = parcial. |
| **Disorder** | Combo entre dos Anomalías de elementos distintos (alto daño). Eje de RF-12. |
| **Shiyu Defense / Deadly Assault / Hollow Zero** | Contenido lategame. Tabla `content_profiles`. |
| **Threshold equip / stock** | Score mínimo para equipar / guardar (defaults 0.75 / 0.50). RF-04 §12.3. |
| **Anti-shill** | Equipo objetivamente mejor que el "shilleado" por la comunidad (flag en `team_compositions`). |
| **DaniBOD** | El usuario / cuenta del jugador (UID 1000860143). Tu único usuario. |
| **CRIT** | Criminal Investigation Special Response Team (facción de Seth, Jane, Qingyi, Zhu Yuan, Cissia). |
| **N.E.P.S.** | New Eridu Public Security (organización paraguas que incluye CRIT). |

---

## 8. Cuando cerrés algo, comunicá esto al usuario

Daniel prefiere reportes operativos cortos:
- ✅ Qué hito cerraste.
- 📊 Qué métricas o counts cambiaron en la DB.
- 📝 Qué archivos creaste/modificaste.
- 🚦 Si el siguiente hito está desbloqueado o si quedó algo bloqueado.
- ❓ Cualquier decisión que requiera input suyo (no asumir).

No reportes el plan completo cada vez (él ya lo sabe), reportá **resultado y siguiente paso**.

---

*CLAUDE.md vivo — actualizar cuando se cierre una fase, cambien las RNF, o aparezcan convenciones nuevas. No duplicar contenido del project-context-IA.md ni del roadmap; solo apuntar.*
