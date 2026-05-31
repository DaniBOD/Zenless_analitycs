# Prompt para nueva sesión Claude Code — QA Real con PaddleOCR

> **Uso:** copiá el bloque entre los `---` de abajo y pegalo como primer mensaje en una sesión nueva de Claude Code. Es self-contained: el agente lee la documentación necesaria por sí mismo.

---

Hola Claude. Soy DaniBOD, owner del proyecto `D:\Proyectos\Zenless_analitycs` (DaniBOD ZZZ Analytics). Vengo de cerrar la migración de Python normal + PaddleOCR en una sesión anterior, y ahora necesito ejecutar QA en juego real para validar que PaddleOCR resuelve el no-determinismo de Tesseract sobre los stats S18.

**Antes que nada, leé en este orden:**

1. `CLAUDE.md` (raíz del proyecto) — convenciones operativas, RNF, layout
2. `Documentacion/Dev_IA/2026-05-31_Hito_2.8_Migracion_Python_PaddleOCR.md` — qué pasó en la sesión anterior (la que cierra este chat)
3. `Documentacion/Dev_IA/2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md` — contexto del aggregator + log rol-aware que vas a validar en runtime
4. `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` — RF base de captura

**Estado de partida (verificado al cierre de la sesión 2026-05-31):**

- ✅ Python 3.11.9 instalado en `C:\Users\danie\AppData\Local\Programs\Python\Python311\`
- ✅ Venv del proyecto activo en `D:\Proyectos\Zenless_analitycs\.venv\`
- ✅ Dependencias del `pyproject.toml` instaladas en venv (`pip install -e ".[dev]"` OK)
- ✅ PaddleOCR 2.6.2 + 2.8.1 funcionando (test de import + init exitoso)
- ✅ Suite de tests: **203 passed, 0 failed** (incluidos los 7 `test_extracts_all_11_stats[1-7]` previously-skipped)
- ⚠️ El `.exe` actual en `app/build/dist/DaniBOD_ZZZ_Analytics/` fue buildeado con el Python Windows Store viejo. Hay que rebuildearlo desde el venv nuevo antes del QA real.

**Tu trabajo en esta sesión, en orden:**

### Tarea 1 — Rebuild del `.exe` desde el venv nuevo

El `.exe` actual fue empaquetado con PyInstaller desde el Python viejo (Windows Store) y no incluye los modelos de PaddleOCR del nuevo `~/.paddleocr/`. Necesitamos un build limpio.

1. Localizá el `.spec` de PyInstaller (probablemente `app/build/danibod_zzz_analytics.spec` o similar — buscá en `app/build/`).
2. Verificá que el venv esté activo antes de rebuildear (`(.venv)` en el prompt).
3. Rebuild con `pyinstaller --clean <ruta_spec>`.
4. **Importante:** PyInstaller necesita aprender a empaquetar PaddleOCR. Hay tres cosas que probablemente fallen y vas a tener que resolver:
   - Modelos de PaddleOCR (no se incluyen por defecto — necesitan `--add-data` o configuración en el `.spec`)
   - DLLs nativas de paddlepaddle (`paddle/libs/*.dll`)
   - Submodules dinámicos de paddleocr (uso de `collect_all()` o `hiddenimports`)
5. Si el rebuild falla con errores cripticos de import, investigá si hay un addendum a `tools/migracion_python_normal.md` que ya documente esto. Sino, documentá la solución en un addendum.

**Aceptación de Tarea 1:** el `.exe` arranca, abre la UI principal, detecta la ventana ZZZ por nombre de proceso, y al menos un heartbeat sale en el log.

### Tarea 2 — QA real del flujo S18 con PaddleOCR

Con el `.exe` rebuildeado y ZZZ en pantalla completa:

1. Lanzá el `.exe` (preferentemente vía `tools/run_debug.ps1` para tener `DANIBOD_DUMP_FRAMES=1` activo).
2. Andá al perfil de **Nangong Yu** → tab "Atributos base" (S18).
3. Apretá **F8 una sola vez**.
4. **Resultado esperado** (criterio de éxito):
   ```
   [diag] F8: scan manual forzado
   [pantalla] S18 — Perfil agente Atributos base
   [reconocido] Nangong Yu — Ataque
   [stats] Nv=60 PV=10797 ATK=2531 DEF=925 IMP=138 CR=19.4% CD=93.2% TA=173 MA=305 ER=1.2 TP=12%
   [completo] extracción exitosa - 11/11 stats capturados
   ```
   La línea `[completo]` debe aparecer **al primer F8**, no después de 3-5 como pasaba con Tesseract.

5. Repetí con **Cissia** (Ataque, S-rank Eléctrico) y al menos **un Disruptivo** (Yixuan o Vivian).
   - Para el Disruptivo, esperá `[completo] extracción exitosa - 11/11 stats capturados` también, pero con `fuerza_bruta` en lugar de `tasa_perforacion`.

**Si la primera F8 NO da `[completo]`:**

- Verificá que el log diga `paddleocr` en alguna línea (confirma que está usando el backend correcto, no fallback Tesseract).
- Revisá `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\app.log` para tracebacks completos.
- Dumpeá el frame con `DANIBOD_DUMP_FRAMES=1` y comparalo con los 7 fixtures de `app/tests/fixtures/atributos_base_ejemplo_*.png` — si visualmente son idénticos, el problema es runtime; si difieren, el detector S18 puede estar capturando antes/después del momento ideal.

### Tarea 3 — Validación de RF-04 (captura disco al farmear)

Independiente de S18. Andá a algún contenido que dropee discos:

1. Farmeá 3-5 discos consecutivos (esperá el modal S3 post-farmeo cada vez).
2. Por cada disco, verificá que aparezca el toast con el scoring + decisión 4-vías (Equipar/Mejorar/Reserva/Descartar).
3. Confirmá que `inventory_discs` (tabla DB) recibió las inserts correspondientes: `sqlite3 db\danibod_zzz_v2.db "SELECT COUNT(*) FROM inventory_discs WHERE fecha_captura >= datetime('now', '-1 hour');"`

### Tarea 4 — Reportar y proponer cierre

Generá un doc nuevo en `Documentacion/Dev_IA/` con fecha del día y formato:
`YYYY-MM-DD_Hito_2.8_QA_Real_PaddleOCR.md`

Que incluya:
- TL;DR
- Resultados del rebuild
- Resultados QA real S18 (Nangong, Cissia, Disruptivo) — incluí los logs reales
- Resultados QA real RF-04 — cantidad de discos capturados + decisión
- Issues encontrados (con severidad)
- Recomendación: ¿se puede cerrar Hito 2.8? ¿Hito 2.9 puede arrancar?

**Si todo OK:**
- Actualizá `project-context-IA.md` §4 marcando Hito 2.8 como cerrado sin caveats
- Commit + push siguiendo convención git de CLAUDE.md §3.4
- Proponé scope concreto del Hito 2.9

**Si hay regresiones:**
- NO marques Hito 2.8 cerrado
- Documentá problemas en el reporte
- Sugerí siguiente sesión de debugging con scope acotado

### Reglas no negociables (recordatorio)

- **RNF-01 ETL sin fallas:** si tocás DB, backup previo. Toda mutación dentro de transacción.
- **RNF-02 Análisis minucioso:** si encontrás algo no documentado (ej. PJ con stats raros), dejá `NULL` + flag tentativo, no inventes.
- **RNF-03 ToS HoYoverse:** solo pixels en pantalla. NO usar `pymem`, lectura de memoria, `keyboard.send()`, automatización de input.

### Comunicación

Reportame al cierre con formato corto:
- ✅ Qué cerraste
- 📊 Métricas (stats por captura, latencia, % éxito)
- 📝 Archivos creados/modificados
- 🚦 Estado Hito 2.8 (cerrado / abierto / bloqueado)
- ❓ Cualquier decisión que requiera input (no asumas)

Arrancá leyendo los 4 archivos de la lista inicial. No empieces a tocar nada hasta tener el contexto completo. Si algo en los docs contradice esta sesión, prevalece la doc más reciente (`2026-05-31_Hito_2.8_Migracion_Python_PaddleOCR.md`).

---

**Notas para uso futuro (no parte del prompt):**

- Si el rebuild del `.exe` con PaddleOCR resulta más complejo que 30 min, vale la pena que la sesión genere un addendum dedicado en `tools/migracion_python_normal.md` con la receta PyInstaller específica.
- Si después de Tarea 1 el `.exe` sigue siendo de 804 MB+ con paddleocr incluido, puede ser momento de evaluar reducir bundle (era issue conocido del dev log 2026-05-13).
- Si Tarea 2 muestra que PaddleOCR funciona pero es muy lento (>2s por captura), evaluar si vale la pena reducir resolución antes de OCR o usar modelos más livianos de paddleocr.
