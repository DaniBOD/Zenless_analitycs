# Identidad de badges S17 — hallazgos del QA en vivo + arquitectura correcta · 2026-06-17

> Sesión de QA en vivo instrumentada (`DANIBOD_ID_DIAG`) sobre Nangong Yu (ZZZ v3.0),
> + prueba decisiva de los matchers sobre 20 ejemplos variados
> (`Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla`).
> Consolida lo que sabemos ANTES de planificar la implementación correcta del
> descriptor/embedding para badges. Reemplaza conclusiones previas erróneas (ver §6).

## 0. Contexto rápido
- **Embedding ya DESCARTADO** (E.0, `audit/spike_embedding_20260616.md`): off-the-shelf no
  supera al descriptor en badges reales; el cuello es la LOCALIZACIÓN, no la discriminación.
- ZZZ v3.0: pantallas S17 (detalle de disco) y S18 (stats de agente) **sin cambios de layout**
  (solo se quitó la línea "mejora recomendada" en S18, no afecta detección).

## 1. Las DOS fuentes de identidad del dueño (medido)
En la pantalla S17 (detalle/selección de disco de un agente) hay DOS badges del dueño:

| | Qué es | Muestra | Localización | Matcher |
|---|---|---|---|---|
| **GRID badge** | avatar chico en la esquina de cada TILE de la grilla izquierda (`crop_grid_selected_badge` sobre el tile resaltado) | **el dueño del disco** | **81%** (NOLOC en transición — el anillo no localiza) | **FUERTE** (avatar grande, discrimina bien) |
| **DETAIL badge** | avatar a la derecha de "Nivel 15/15" en el panel de detalle (`crop_detail_badge`) | **el dueño del disco** (NO el agente de la página) | **100%** (fijo, estable, sin NOLOC) | **DÉBIL/ROTO** (avatar chico → imán + abstención) |

**Clave: AMBOS muestran el dueño del disco** (confirmado por el usuario: al seleccionar un
candidato de Yanagi en la página de Nangong Yu, sale **Yanagi** tanto en grid como en detail).

## 2. QA en vivo — 32 discos (Nangong Yu, navegación deliberada)
- **Localización:** grid 26/32 = **81%**, detail 32/32 = **100%**, ninguno 0%.
- **Voto (grid+detail) vs equip_map:** ✅62% · ❌**WRONG 12%** (4 discos) · ⬜incierto 25%.
- **Voto SOLO grilla (sin detail):** ✅62% · ❌**WRONG 0%** · ⬜incierto 38%.
- **Flujo-ancla (equipados):** 6/6 ✅, 0 ❌.
- **Los 4 WRONG fueron todos "Nangong Yu" falso** (sobre discos de Seth/Vivian/Grace), y vinieron
  del **detail-badge** (`det_votes=[Nangong Yu:0.81]`).

## 3. Prueba decisiva del matcher (offline, 20 ejemplos variados, librería persistida)
Corriendo los matchers REALES (`identify_s17` grid vs `s17_match_detail`) sobre los 20 ejemplos:

| Matcher | Distribución de lo que identificó |
|---|---|
| **GRID** | Rina, Burnice, Vivian, Soukaku, Yuzuha, Piper, Nangong Yu — **7 dueños variados y CORRECTOS** |
| **DETAIL** | **solo "Nangong Yu" (5×) o abstención (15×)** — **NUNCA** acertó otro PJ |

→ El detail-matcher tiene un **"imán Nangong Yu"** + sobre-abstención. NO es el aprendizaje en vivo
(esto es offline con la librería persistida `avatar_detbadge_v2.npz`, 316 refs / 47 PJs). Es el
**matcher + librería del detail** que es débil: el avatar de detalle es chico → el descriptor no
discrimina → cae al imán o se abstiene bajo el guard 0.80.

## 4. Diagnóstico: cada superficie tiene UN problema distinto
- **GRID:** matcher FUERTE, pero **localización 81%** (el anillo de selección no localiza en
  transición — cuello ya diagnosticado en `audit/localizacion_diag_20260616.md`).
- **DETAIL:** localización **100%** (su gran ventaja), pero **matcher DÉBIL** (imán + abstención;
  avatar chico, ~55%@0-wrong offline, ver `audit/detbadge_vs_grid_20260617.md`).

## 5. Implicancias para la implementación correcta (a planificar)
- **RNF-02 inmediato:** el imán del detail mete WRONGS. Hoy, **solo-grilla da 0 wrong**. Mientras el
  detail-matcher no se arregle, NO debe poder pisar el voto del grid.
- **Dirección del usuario (estratégica):** dar **énfasis al DETAIL** (porque localiza 100% vs grid
  81%), usar el grid como "plus" del match, y —si el detail llega a ser lo bastante bueno— eventualmente
  retirar el código del grid (solo con 100% de confianza en el detail). Esto requiere PRIMERO arreglar
  el matcher del detail.
- **Palanca propuesta por el usuario (two-stage):** recortar un área general del badge y luego
  REFINAR a un crop limpio/centrado (como el del grid) antes de matchear → subiría la discriminación
  del detail. Es la idea correcta: el descriptor anda al 92% con crops grid limpios; el detail falla
  por crop chico/sucio, no porque la señal no esté.
- **Preguntas abiertas para el planning:**
  1. ¿Por qué el imán Nangong Yu? (¿librería sucia/desbalanceada? ¿crops de detail mal localizados a
     una zona Nangong-Yu? ¿avatar tan chico que el descriptor colapsa al ref "promedio"?) — investigar
     composición y calidad de `avatar_detbadge_v2.npz`.
  2. ¿Two-stage refine del detail sube la discriminación lo suficiente para volverlo primario?
  3. ¿Re-cosechar una librería de detail LIMPIA (crops refinados) cambia el resultado?
  4. ¿Combinar grid (cuando localiza, fuerte) + detail (siempre localiza) por voto, con el detail
     SOLO sumando cuando supera un guard alto, da 0-wrong + alto yield?
  5. ¿El embedding —ya descartado para grid— tendría sentido SOLO para el detail (avatares chicos)?
     (Probablemente no: el spike mostró que colapsa más en crops chicos/degradados.)

## 6. Conclusiones previas CORREGIDAS (no repetir los errores)
- ❌ "El detail-badge muestra el agente de la página, no el dueño." **FALSO.** Muestra el dueño del
  disco (Yanagi en el ejemplo del usuario). El síntoma de "todo Nangong Yu" era el **imán del matcher**,
  no la señal. (El error vino de que en la sesión el detail votaba siempre Nangong Yu → asumí señal,
  era matcher.)
- ❌ "El spike offline validó el detail al 95%." **Confundido:** los crops del harvest eran SIEMPRE el
  agente matcheando su propio disco equipado → no probaba candidatos.

## 7. Infraestructura / estado del repo
- **Instrumentación:** `DANIBOD_ID_DIAG` en `monitor.py::_log_id_diag` (loguea `[id_diag]` por disco:
  grid/det loc+match+voto+assigned, con `id` = clave equip_map), switch `qa_launch -IdDiag`, parser
  `tools/parse_id_diag.py` (cruza vs `audit/equip_map_20260612.json`).
- **Build:** el `.exe` de `app/build/dist` está VIEJO (sin instrumentación). Para QA instrumentado se
  corrió **desde fuente**: `.venv\Scripts\python.exe -m app.main` con `DANIBOD_DB_PATH`/`READONLY`/
  `ID_DIAG`. (Rebuild pendiente si se quiere el .exe al día.)
- **`tools/extract_harvest_badges.py`:** corregido a S17 para el det (antes S18 = ruido). Los
  `audit/harvest_badges/*__det__*` commiteados en d382def eran los viejos malos; regenerados local.
- **S18 v3.0 (regresión menor, aparte):** detecta OK (conf 0.96-0.98) pero el parseo a veces pierde PV,
  una vez leyó Nv=15 (disco) en vez de 60 (agente), y siempre pierde TP (=0%). No bloquea badges.
- Datasets: `audit/harvest_badges/` (grid+det, label-latch), `audit/equip_map_20260612.json` (verdad),
  `Documentacion/Screenshots_Triggers/Discos_Triggers/16_discos_pj_grilla/` (20 ejemplos variados).
