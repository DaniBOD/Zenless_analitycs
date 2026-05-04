"""
Diagramas v4 — Top-down decomposition.

Cada RF se segmenta en 2-3 sub-diagramas:
- _01_overview: vista de alto nivel con nodos ABSTRACT que referencian
                sub-diagramas hermanos.
- _02 / _03 / ...: profundizan procesos específicos.

Nodos ABSTRACT tienen borde doble + label "Ver: RF-XX_NN_subprocess" para
indicar que se profundiza en otro diagrama.

Diagramas generados (14):
  RF-04_01_overview, RF-04_02_extraccion, RF-04_03_analisis
  RF-05_01_overview, RF-05_02_diff
  RF-06_01_overview, RF-06_02_algoritmo
  RF-12_01_runtime, RF-12_02_catalogacion
  RF-13_01_captura, RF-13_02_tierlist, RF-13_03_bayesiano
  RF-14_01_overview, RF-14_02_buildfull

Output: SVG + PNG en Documentacion/Diagramas de flujos/
"""
from graphviz import Digraph
import os

scratch = "/sessions/blissful-adoring-pasteur/diagramas_scratch_v4"
os.makedirs(scratch, exist_ok=True)

# Paleta consistente con v3
TRIGGER  = dict(style="filled,rounded", fillcolor="#ffe4b5", color="#d97706", shape="box")
PROCESS  = dict(style="filled,rounded", fillcolor="#e0f2fe", color="#0369a1", shape="box")
DECISION = dict(style="filled",         fillcolor="#fef3c7", color="#a16207", shape="diamond")
TERMINAL = dict(style="filled,rounded", fillcolor="#dcfce7", color="#15803d", shape="box")
ALERT    = dict(style="filled,rounded", fillcolor="#fee2e2", color="#b91c1c", shape="box")
START    = dict(style="filled",         fillcolor="#f3e8ff", color="#7c3aed", shape="oval")
EVAL     = dict(style="filled,rounded", fillcolor="#cffafe", color="#0e7490", shape="box")
RECO     = dict(style="filled,rounded", fillcolor="#dcfce7", color="#15803d", shape="box")
AI       = dict(style="filled,rounded", fillcolor="#fbcfe8", color="#9d174d", shape="box")
BAYES    = dict(style="filled,rounded", fillcolor="#e9d5ff", color="#6b21a8", shape="box")
DB       = dict(style="filled,rounded", fillcolor="#f1f5f9", color="#475569", shape="cylinder")
# Nodo ABSTRACT: borde doble, color distintivo, label con referencia
ABSTRACT = dict(style="filled,rounded,bold", fillcolor="#fff7ed", color="#c2410c",
                shape="box", penwidth="3")

def newg(name, title):
    g = Digraph(name, format="svg")
    g.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
           label=title, labelloc="t", fontsize="13")
    g.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
    g.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")
    return g

# Helper para nodo abstract con referencia
def abstract(g, name, label, ref):
    g.node(name, f"{label}\n\n📂 Ver: {ref}", **ABSTRACT)

# =============================================================================
# RF-04 — CAPTURA DE DISCOS (3 niveles)
# =============================================================================

# --- RF-04_01_overview ---
g = newg("RF04_01", "RF-04 — Captura de discos · OVERVIEW (alto nivel)")
g.node("Start", "Usuario en ZZZ", **START)
g.node("Trigger", "¿Trigger?\n(F8 / poll / focus / NEW!)", **DECISION)
g.node("Classify", "Clasificar pantalla\n(template matching)", **PROCESS)
g.node("ScreenType", "¿Tipo de pantalla\nrelevante?", **DECISION)
g.node("Discard", "Descartar\n(menú/diálogo/combate)", **ALERT)
abstract(g, "Extract", "EXTRACCIÓN de datos\nsegún origen", "RF-04_02_extraccion")
abstract(g, "Analyze", "ANÁLISIS y scoring\ndel disco", "RF-04_03_analisis")
g.node("Persist", "INSERT/UPDATE en\ninventory_discs +\ninventory_disc_evaluations", **DB)
g.node("Notify", "Emitir toast\nUI (RF-11)", **TERMINAL)

g.edge("Start", "Trigger")
g.edge("Trigger", "Classify", label="dispara")
g.edge("Classify", "ScreenType")
g.edge("ScreenType", "Discard", label="no")
g.edge("ScreenType", "Extract", label="sí")
g.edge("Extract", "Analyze")
g.edge("Analyze", "Persist")
g.edge("Persist", "Notify")
diagrams = [(g, "RF-04_01_overview")]

# --- RF-04_02_extraccion ---
g = newg("RF04_02", "RF-04 · EXTRACCIÓN — los 3 caminos según origen")
g.node("Entry", "Pantalla relevante\nclasificada", **START)
g.node("Origen", "¿Origen?", **DECISION)

# Patrulla
g.node("Patrulla", "Resultados Desafío\n(Patrulla de Área)", **PROCESS)
g.node("AutoDis", "¿Toggle Desmontaje\nautomático?", **DECISION)
g.node("WarnAuto", "Marcar como\ndisco auto-descartable", **ALERT)
g.node("GridP", "Extraer grid drops:\nemblema + rareza + slot", **PROCESS)
g.node("ModalP", "¿Usuario abre\nmodal?", **DECISION)
g.node("PreRegP", "Pre-registro\n(sin substats aún)", **PROCESS)
g.node("FullP", "Lectura completa\nmain + 4 subs + nivel", **PROCESS)

# Tienda Música
g.node("Tienda", "Tienda Música\n(Afinación)", **PROCESS)
g.node("AfinarA", "Usuario 'Afinar ×01/×06'", **PROCESS)
g.node("ResAfin", "Resultado afinación\n(grid 2×3)", **PROCESS)
g.node("OpenT", "¿Abre tile?", **DECISION)
g.node("PanelT", "Panel izquierdo\nmuestra detalle", **PROCESS)
g.node("FullT", "Vista detallada\npantalla completa", **PROCESS)

# Inventario / Agente (swap)
g.node("InvA", "Vista Agente o\nInventario discos", **PROCESS)
g.node("DiffH", "Hash build vs DB", **PROCESS)
g.node("Changed", "¿Build cambió?", **DECISION)
g.node("NoCh", "Sin cambios\n(ignorar)", **TERMINAL)
g.node("OCRSwap", "OCR sobre slot\ncambiado", **PROCESS)

# Salida
g.node("OutData", "Disco normalizado:\n{set, slot, main, subs+rolls,\nnivel, source}", **TERMINAL)

g.edge("Entry", "Origen")
g.edge("Origen", "Patrulla", label="Patrulla")
g.edge("Origen", "Tienda", label="Música")
g.edge("Origen", "InvA", label="Agente/Inv")

g.edge("Patrulla", "AutoDis")
g.edge("AutoDis", "WarnAuto", label="sí")
g.edge("AutoDis", "GridP", label="no")
g.edge("WarnAuto", "GridP")
g.edge("GridP", "ModalP")
g.edge("ModalP", "PreRegP", label="no")
g.edge("ModalP", "FullP", label="sí")
g.edge("PreRegP", "OutData")
g.edge("FullP", "OutData")

g.edge("Tienda", "AfinarA")
g.edge("AfinarA", "ResAfin")
g.edge("ResAfin", "OpenT")
g.edge("OpenT", "PanelT", label="tile")
g.edge("OpenT", "FullT", label="Detalles")
g.edge("PanelT", "OutData")
g.edge("FullT", "OutData")

g.edge("InvA", "DiffH")
g.edge("DiffH", "Changed")
g.edge("Changed", "NoCh", label="no")
g.edge("Changed", "OCRSwap", label="sí")
g.edge("OCRSwap", "OutData")
diagrams.append((g, "RF-04_02_extraccion"))

# --- RF-04_03_analisis ---
g = newg("RF04_03", "RF-04 · ANÁLISIS — scoring engine y recomendación")
g.node("InData", "Disco normalizado\n(de RF-04_02)", **START)

g.node("BMatch", "Build-match contra\nagent_discs (45 PJs)", **EVAL)
g.node("CompatPJs", "Lista de PJs\ncompatibles\n(set + slot + main)", **PROCESS)
g.node("AltPJs", "PJs alternativos\n(arquetipo compatible)", **PROCESS)

g.node("ArchPrim", "Detectar arquetipo\nprimario del disco\n(set → archetype)", **EVAL)
g.node("ArchSec",  "Arquetipo secundario\n(si dual)", **EVAL)

g.node("ScoreCalc", "Calcular score:\nΣ(peso·(1+rolls·0.25))\n− Σ(|peso_neg|·(1+rolls·0.5))\n+ bonus_main + bonus_nivel", **EVAL)

g.node("ThrEquip", "score ≥\nthreshold_equip\ndel mejor PJ?", **DECISION)
g.node("ThrUpg", "score ≥\nthreshold_upgrade\nde algún PJ?", **DECISION)
g.node("ThrStock", "score ≥\nthreshold_stock\ndel arquetipo?", **DECISION)

g.node("RecEq",  "🟢 EQUIPAR\nal PJ X", **RECO)
g.node("RecUp",  "🔵 MEJORAR\nbuild de PJ Y", **RECO)
g.node("RecRes", "🟡 RESERVA\narquetipo Z", **RECO)
g.node("RecDis", "🔴 DESCARTAR", **ALERT)

g.node("Out", "Recomendación\n+ desglose JSON", **TERMINAL)

g.edge("InData", "BMatch")
g.edge("BMatch", "CompatPJs")
g.edge("CompatPJs", "AltPJs")
g.edge("AltPJs", "ArchPrim")
g.edge("ArchPrim", "ArchSec")
g.edge("ArchSec", "ScoreCalc")
g.edge("ScoreCalc", "ThrEquip")
g.edge("ThrEquip", "RecEq",  label="sí")
g.edge("ThrEquip", "ThrUpg", label="no")
g.edge("ThrUpg", "RecUp",  label="sí")
g.edge("ThrUpg", "ThrStock", label="no")
g.edge("ThrStock", "RecRes", label="sí")
g.edge("ThrStock", "RecDis", label="no")
g.edge("RecEq",  "Out")
g.edge("RecUp",  "Out")
g.edge("RecRes", "Out")
g.edge("RecDis", "Out")
diagrams.append((g, "RF-04_03_analisis"))

# =============================================================================
# RF-05 — UPGRADE DE DISCOS (2 niveles)
# =============================================================================

# --- RF-05_01_overview ---
g = newg("RF05_01", "RF-05 — Upgrade de discos · OVERVIEW")
g.node("StartU", "Usuario va a subir\nnivel de disco", **START)
g.node("CapPRE", "Captura PRE\n(estado actual)", **PROCESS)
g.node("Source", "¿Origen del upgrade?", **DECISION)
g.node("Modal", "Modal desde\nAgente/Inventario", **PROCESS)
g.node("FullS", "Pantalla completa\nTienda Música", **PROCESS)
g.node("UpAct", "Usuario confirma\nupgrade (×1 / ×3 / max)", **PROCESS)
g.node("CapPOST", "Captura POST\n(estado nuevo)", **PROCESS)
abstract(g, "Diff", "DIFF PRE/POST\ny clasificación\nde la mejora", "RF-05_02_diff")
g.node("Eval", "Re-evaluar disco\n(invocar RF-04 análisis)", **EVAL)
g.node("Persist", "UPDATE inventory_discs\n+ INSERT evaluation", **DB)
g.node("Notify", "Toast con delta\nde score", **TERMINAL)

g.edge("StartU", "CapPRE")
g.edge("CapPRE", "Source")
g.edge("Source", "Modal", label="modal")
g.edge("Source", "FullS", label="full")
g.edge("Modal", "UpAct")
g.edge("FullS", "UpAct")
g.edge("UpAct", "CapPOST")
g.edge("CapPOST", "Diff")
g.edge("Diff", "Eval")
g.edge("Eval", "Persist")
g.edge("Persist", "Notify")
diagrams.append((g, "RF-05_01_overview"))

# --- RF-05_02_diff ---
g = newg("RF05_02", "RF-05 · DIFF PRE/POST — clasificación de la mejora")
g.node("In", "PRE + POST\n(de RF-05_01)", **START)
g.node("Sub4Pre", "¿sub4 estaba\ndesbloqueada\nen PRE?", **DECISION)
g.node("CountSub4", "Contar substats\nen POST", **EVAL)
g.node("Has4", "POST tiene 4\nsubstats?", **DECISION)
g.node("SubUnlock", "🆕 sub_unlocked\n(nivel 9 o 12 alcanzado:\ndesbloquea sub4)", **EVAL)
g.node("DiffRolls", "Diff rolls de subs\nentre PRE y POST", **EVAL)
g.node("OneRoll", "Cambió 1 roll?", **DECISION)
g.node("SubRoll", "🎯 sub_rolled\n(un roll +N agregado\na un sub existente)", **EVAL)
g.node("MultiRoll", "🎲 multi_rolls\n(varios rolls a la vez:\nupgrade ×3 / max)", **EVAL)
g.node("OutDiff", "Salida:\n{tipo, rolls_added,\ndelta_score}", **TERMINAL)

g.edge("In", "Sub4Pre")
g.edge("Sub4Pre", "CountSub4", label="no")
g.edge("Sub4Pre", "DiffRolls", label="sí")
g.edge("CountSub4", "Has4")
g.edge("Has4", "SubUnlock", label="sí")
g.edge("Has4", "DiffRolls", label="no")
g.edge("SubUnlock", "OutDiff")
g.edge("DiffRolls", "OneRoll")
g.edge("OneRoll", "SubRoll", label="sí")
g.edge("OneRoll", "MultiRoll", label="no")
g.edge("SubRoll", "OutDiff")
g.edge("MultiRoll", "OutDiff")
diagrams.append((g, "RF-05_02_diff"))

# =============================================================================
# RF-06 — OPTIMIZADOR DE BUILD (2 niveles)
# =============================================================================

# --- RF-06_01_overview ---
g = newg("RF06_01", "RF-06 — Optimizador de build · OVERVIEW")
g.node("S1", "Trigger manual\n(panel PJ)", **START)
g.node("S2", "Trigger automático\n(post RF-04, score≥thr)", **START)
g.node("Deb", "Debounce 2s/PJ", **DECISION)
g.node("Load", "Cargar:\nPJ + arquetipo + thresholds\n+ inventory_discs\n+ build actual + preferences", **PROCESS)
abstract(g, "Algo", "ALGORITMO\ngreedy + bonus pass", "RF-06_02_algoritmo")
g.node("Top3", "Top 3 builds\nrankeadas por score", **RECO)
g.node("Persist", "INSERT en\noptimizer_pending_actions", **DB)
g.node("Notify", "Notificar UI", **TERMINAL)
g.node("Skip", "Skipear\n(suprimido por debounce)", **ALERT)

g.edge("S1", "Deb")
g.edge("S2", "Deb")
g.edge("Deb", "Load", label="OK")
g.edge("Deb", "Skip", label="suprimido")
g.edge("Load", "Algo")
g.edge("Algo", "Top3")
g.edge("Top3", "Persist")
g.edge("Persist", "Notify")
diagrams.append((g, "RF-06_01_overview"))

# --- RF-06_02_algoritmo ---
g = newg("RF06_02", "RF-06 · ALGORITMO — greedy por slot + bonus pass")
g.node("In", "Inputs cargados\n(de RF-06_01)", **START)

# Greedy
g.node("GLoop", "GREEDY: para cada slot 1-6", **EVAL)
g.node("Score1", "Score local de cada\ncandidato del inventario\n(scoring engine)", **EVAL)
g.node("TopK", "Top-K por slot (K=8)\n→ candidate pool 6×8", **EVAL)

# Bonus pass
g.node("BPass", "BONUS PASS — explorar\ncombinaciones de set bonus", **EVAL)
g.node("C42", "4pc + 2pc\n(set primario + sec)", **PROCESS)
g.node("C222", "2 + 2 + 2\n(stats puros)", **PROCESS)
g.node("C33", "3 + 3\n(casos especiales)", **PROCESS)

g.node("ScoreF", "Score conjunto =\nΣ slots + bonus_set\n+ bonus_thresholds_PJ\n(ATK/IMP/PEN caps)", **EVAL)

# Comparación
g.node("Delta", "Delta vs build\nactual del PJ", **PROCESS)
g.node("CheckSwap", "¿Discos vienen\nde otros PJs?", **DECISION)
g.node("DualDelta", "Calcular delta dual:\nlo que pierde origen,\nlo que gana destino", **EVAL)
g.node("Sort", "Ordenar combinaciones\nglobalmente por score", **EVAL)
g.node("Out", "Top 3 builds\n+ desglose + swaps", **TERMINAL)

g.edge("In", "GLoop")
g.edge("GLoop", "Score1")
g.edge("Score1", "TopK")
g.edge("TopK", "BPass")
g.edge("BPass", "C42")
g.edge("BPass", "C222")
g.edge("BPass", "C33")
g.edge("C42",  "ScoreF")
g.edge("C222", "ScoreF")
g.edge("C33",  "ScoreF")
g.edge("ScoreF", "Delta")
g.edge("Delta", "CheckSwap")
g.edge("CheckSwap", "DualDelta", label="sí")
g.edge("CheckSwap", "Sort", label="no")
g.edge("DualDelta", "Sort")
g.edge("Sort", "Out")
diagrams.append((g, "RF-06_02_algoritmo"))

# =============================================================================
# RF-12 — TEAM-AWARE (2 diagramas, ya semi-segmentado)
# =============================================================================

# --- RF-12_01_runtime ---
g = newg("RF12_01", "RF-12 · RUNTIME — lookup determinista (3 capas)")
g.node("Start", "Usuario abre optimizador\ncon team_context\n[pj, comp1, comp2]", **START)
g.node("Lookup", "Lookup team_synergies\npara pares\n(pj,comp1) y (pj,comp2)", **DB)
g.node("CapaA", "CAPA A —\nOverride de pesos\nde substats", **EVAL)
g.node("Pondera", "Si dos pares overridean\nmisma stat:\nponderar por confianza", **EVAL)
g.node("CapaB", "CAPA B —\nOverride de set recomendado\n(si confianza ≥ 0.7)", **EVAL)
g.node("CapaC", "CAPA C — opcional\nLookup team_compositions\ntop-N por pj_principal", **DB)
g.node("CallRF06", "Invocar RF-06\ncon pesos/set ajustados\n→ ver RF-06_01", **PROCESS)
g.node("Out", "Top 3 builds\n+ justificación de overrides\n+ sinergias activadas", **RECO)

g.edge("Start", "Lookup")
g.edge("Lookup", "CapaA")
g.edge("CapaA", "Pondera")
g.edge("Pondera", "CapaB")
g.edge("CapaB", "CapaC")
g.edge("CapaC", "CallRF06")
g.edge("CallRF06", "Out")
diagrams.append((g, "RF-12_01_runtime"))

# --- RF-12_02_catalogacion ---
g = newg("RF12_02", "RF-12 · CATALOGACIÓN — Claude API offline")
g.node("Start", "Trigger:\non-demand /\nPJ nuevo (RF-04) /\nset nuevo", **START)
g.node("Cap", "¿Cap de costo\nmensual excedido?", **DECISION)
g.node("Pause", "Pausar cola\n+ notificar al usuario", **ALERT)
g.node("Enq", "Encolar lote\n(reusa prompt cache)", **PROCESS)
g.node("Sonnet", "Claude sonnet:\nteam_synergy_pair\n(990 pares posibles)", **AI)
g.node("Opus", "Claude opus:\nteam_composition_topN\n(45 PJs × top-5)", **AI)
g.node("Validate", "Validar response JSON\n+ schema match", **EVAL)
g.node("Retry", "Retry con\nbackoff", **ALERT)
g.node("InsSyn", "INSERT/UPDATE\nteam_synergies", **DB)
g.node("InsComp", "INSERT/UPDATE\nteam_compositions", **DB)
g.node("Audit", "INSERT en ai_catalog_runs\n(tokens, costo, ms)", **DB)
g.node("ConfInit", "Marcar pares como\nconfianza inicial = 0.85\n(tipico para sonnet)", **PROCESS)
g.node("Done", "Listo: sinergias\ndisponibles para\nRF-12_01 runtime", **TERMINAL)

g.edge("Start", "Cap")
g.edge("Cap", "Pause", label="sí")
g.edge("Cap", "Enq", label="no")
g.edge("Enq", "Sonnet")
g.edge("Enq", "Opus")
g.edge("Sonnet", "Validate")
g.edge("Opus", "Validate")
g.edge("Validate", "Retry", label="error")
g.edge("Retry", "Sonnet", style="dashed")
g.edge("Validate", "InsSyn", label="ok")
g.edge("Validate", "InsComp", label="ok")
g.edge("InsSyn", "Audit")
g.edge("InsComp", "Audit")
g.edge("Audit", "ConfInit")
g.edge("ConfInit", "Done")
diagrams.append((g, "RF-12_02_catalogacion"))

# =============================================================================
# RF-13 — VALIDACIÓN LATEGAME (3 diagramas)
# =============================================================================

# --- RF-13_01_captura ---
g = newg("RF13_01", "RF-13 · CAPTURA — registro manual de runs (F11)")
g.node("End", "Usuario termina\nrun Shiyu/DA", **START)
g.node("F11", "Hotkey F11", **TRIGGER)
g.node("Shot1", "Capturar resumen\n(estrellas, tiempo, equipo)", **PROCESS)
g.node("Toast1", "Toast pide:\n'Navegar a Battle Stats'", **PROCESS)
g.node("Shot2", "Capturar Battle Stats\n(breakdown DMG)", **PROCESS)
g.node("OCR", "OCR híbrido\n(Tesseract texto +\nPaddleOCR números)\n→ ver RF-09 (OCR backend)", **EVAL)
g.node("Valid", "Validar consistencia:\n• ΣDMG% ≈ 100\n• PJs match roster\n• ciclo activo en fecha", **DECISION)
g.node("ManCorr", "Modal de\ncorrección manual", **ALERT)
g.node("Insert", "INSERT lategame_runs\n+ lategame_run_damage", **DB)
g.node("Toast2", "Toast confirma\nrun registrado", **TERMINAL)
g.node("Counter", "¿runs_nuevos ≥ 3\nen ventana?", **DECISION)
abstract(g, "TierTrig", "DISPARAR\nRECÁLCULO TIER", "RF-13_02_tierlist")
abstract(g, "BayesTrig", "EVALUAR\nRETRO-FEEDBACK", "RF-13_03_bayesiano")

g.edge("End", "F11")
g.edge("F11", "Shot1")
g.edge("Shot1", "Toast1")
g.edge("Toast1", "Shot2")
g.edge("Shot2", "OCR")
g.edge("OCR", "Valid")
g.edge("Valid", "ManCorr", label="falla")
g.edge("Valid", "Insert", label="ok")
g.edge("ManCorr", "Insert")
g.edge("Insert", "Toast2")
g.edge("Insert", "Counter")
g.edge("Counter", "TierTrig", label="sí")
g.edge("Insert", "BayesTrig", label="trigger lookup")
diagrams.append((g, "RF-13_01_captura"))

# --- RF-13_02_tierlist ---
g = newg("RF13_02", "RF-13 · TIER LIST — recálculo + delta vs Prydwen")
g.node("Trig", "Trigger:\nN=3 nuevos /\non-demand /\nsemanal D03:00", **START)
g.node("Snap", "Generar nuevo\nsnapshot_id (atómico)", **PROCESS)
g.node("Loop", "Para cada (pj, contenido):", **EVAL)
g.node("Agg", "Agregar últimos\nK=20 runs\n(K_min=3 para emitir)", **EVAL)
g.node("Score", "Score normalizado:\nrate_3★ × 0.45 +\nwin × 0.20 +\ndmg_share × 0.20 +\ntiempo × 0.15", **EVAL)
g.node("Bucket", "Asignar tier por\nbuckets fijos:\nS+ ≥90 / S 80-89 /\nA 65-79 / B 50-64 /\nC 30-49 / D ≤29", **EVAL)
g.node("Pry", "Lookup\nprydwen_tier_snapshots\n(más reciente)", **DB)
g.node("Delta", "Calcular delta:\n(+2/+1/=/-1/-2)", **PROCESS)
g.node("Justif", "Generar justificación\n(plantilla por delta:\ncausa probable, mindscape,\nbuild status)", **PROCESS)
g.node("Insert", "INSERT en\ntier_list_personal\n(con snapshot_id)", **DB)
g.node("Notify", "Notificar UI:\n'tier list recalculada\n+ X cambios detectados'", **TERMINAL)

g.edge("Trig", "Snap")
g.edge("Snap", "Loop")
g.edge("Loop", "Agg")
g.edge("Agg", "Score")
g.edge("Score", "Bucket")
g.edge("Bucket", "Pry")
g.edge("Pry", "Delta")
g.edge("Delta", "Justif")
g.edge("Justif", "Insert")
g.edge("Insert", "Notify")
diagrams.append((g, "RF-13_02_tierlist"))

# --- RF-13_03_bayesiano ---
g = newg("RF13_03", "RF-13 · RETRO-FEEDBACK BAYESIANO — ajuste de team_synergies.confianza")
g.node("Run", "Nuevo lategame_run\ninsertado\n(de RF-13_01)", **START)
g.node("Match", "Equipo del run\ncoincide con par\nde team_synergies?", **DECISION)
g.node("Skip", "Sin acción\n(par no recomendado)", **TERMINAL)
g.node("Acc", "Acumular evidencia\npor par afectado\n(últimos 90 días)", **PROCESS)
g.node("Enough", "≥ 3 runs\nde evidencia?", **DECISION)
g.node("Wait", "Esperar más runs\n(incertidumbre alta)", **TERMINAL)

g.node("Like", "Likelihood =\nrate_3★_obs / 0.75\n(esperado para sinergia)\nCAP en 1.5", **BAYES)
g.node("Prior", "Peso prior =\n1 / (1 + 0.3·N)\n(decrece con evidencia)", **BAYES)
g.node("Post", "Confianza_post =\nprior·conf_ai +\n(1−prior)·likelihood\nclip(0,1)", **BAYES)

g.node("Cong", "Sinergia\ncongelada por\nuser?", **DECISION)
g.node("SkipC", "Skip:\noverride manual\nrespetado", **TERMINAL)
g.node("Update", "UPDATE\nteam_synergies.confianza\n+ INSERT en\nteam_synergy_adjustments", **DB)
g.node("CheckThr", "confianza < 0.7?", **DECISION)
g.node("Disable", "Marcar override\nde RF-12 como\nno aplicable", **ALERT)
g.node("Badge", "Badge ±RF-13\nen panel Equipos\n(verde sube / rojo baja)", **TERMINAL)

g.edge("Run", "Match")
g.edge("Match", "Skip", label="no")
g.edge("Match", "Acc", label="sí")
g.edge("Acc", "Enough")
g.edge("Enough", "Wait", label="no")
g.edge("Enough", "Like", label="sí")
g.edge("Like", "Prior")
g.edge("Prior", "Post")
g.edge("Post", "Cong")
g.edge("Cong", "SkipC", label="sí")
g.edge("Cong", "Update", label="no")
g.edge("Update", "CheckThr")
g.edge("CheckThr", "Disable", label="sí")
g.edge("CheckThr", "Badge", label="no")
g.edge("Disable", "Badge")
diagrams.append((g, "RF-13_03_bayesiano"))

# =============================================================================
# RF-14 — OPTIMIZADOR DE ARMAS (2 niveles)
# =============================================================================

# --- RF-14_01_overview ---
g = newg("RF14_01", "RF-14 · OVERVIEW — scoring contextual + ranking")
g.node("Start", "Usuario abre optimizador\ncon PJ + contenido\n(Shiyu/DA/HZ/general)", **START)
g.node("Cache", "¿Existe en\nweapon_evaluations\n(snapshot vigente)?", **DECISION)
g.node("Lookup", "Lookup directo\n(< 5 ms)", **DB)

g.node("Load", "Cargar:\nPJ + content_profile\n+ pj_weapon_synergy\n+ catálogo (49 W) + inventario", **PROCESS)
g.node("Loop", "Para cada arma:", **EVAL)
g.node("ScoreATK", "score_atk_base + stat₂\n(lineal, 25+15 pts)", **EVAL)
g.node("PassLoop", "Por cada pasiva:\ncalcular uptime contextual\n× modifier × stat_impact_pj", **EVAL)
g.node("ScoreT", "+ score_textual\n(override manual)\n+ score_synergy_pj", **EVAL)
g.node("Total", "Score total\n(ATK 25 + stat₂ 15 +\npasivas 40 + texto 10\n+ synergy 10 = 100)", **EVAL)

g.node("Pry", "Lookup\nprydwen_weapon_snapshots\n+ delta", **DB)
g.node("RankI", "Ranking IDEAL\n(catálogo 49)", **RECO)
g.node("RankD", "Ranking DISPONIBLE\n(inventario)", **RECO)
g.node("Persist", "INSERT\nweapon_evaluations\n(snapshot)", **DB)

g.node("BFQ", "¿Modo Build Full?", **DECISION)
abstract(g, "BF", "BUILD FULL\n(arma + 6 discos)", "RF-14_02_buildfull")
g.node("Out", "Output → UI\n(4 sub-pestañas)", **TERMINAL)

g.edge("Start", "Cache")
g.edge("Cache", "Lookup", label="sí")
g.edge("Cache", "Load", label="no")
g.edge("Lookup", "Out")
g.edge("Load", "Loop")
g.edge("Loop", "ScoreATK")
g.edge("ScoreATK", "PassLoop")
g.edge("PassLoop", "ScoreT")
g.edge("ScoreT", "Total")
g.edge("Total", "Pry")
g.edge("Pry", "RankI")
g.edge("Pry", "RankD")
g.edge("RankI", "Persist")
g.edge("RankD", "Persist")
g.edge("Persist", "BFQ")
g.edge("BFQ", "BF", label="sí")
g.edge("BFQ", "Out", label="no")
g.edge("BF", "Out")
diagrams.append((g, "RF-14_01_overview"))

# --- RF-14_02_buildfull ---
g = newg("RF14_02", "RF-14 · BUILD FULL — combinación arma + 6 discos (RF-06 + RF-14)")
g.node("In", "PJ + contenido\n+ ranking armas\n(de RF-14_01)", **START)
g.node("Top3W", "Tomar top 3 armas\n(score más alto)", **EVAL)
g.node("Loop", "Para cada arma:\ninvocar RF-06\ncon stats efectivos\n(PJ + arma equipada)", **PROCESS)
g.node("RF06ref", "→ ver RF-06_01\n(devuelve 3 builds)", **ABSTRACT)
g.node("Combo", "Score conjunto:\n• ATK total vs caps\n• CRIT cap (100%)\n• thresholds soporte\n  (Astra 3429, Ju Fufu 3400)\n• ER awakenings\n  (Burnice ER ≥ 1.8)", **EVAL)
g.node("Inter", "Aplicar interacciones:\npenaliza CRIT overflow,\nbonifica threshold hit", **EVAL)
g.node("Sort", "Ordenar 9 combinaciones\n(3 armas × 3 builds)\nglobalmente", **EVAL)
g.node("Top3F", "Top 3 combinaciones\nfull (arma + 6 discos)", **RECO)
g.node("Out", "Output con desglose:\narma + slots + delta\nvs build actual", **TERMINAL)

g.edge("In", "Top3W")
g.edge("Top3W", "Loop")
g.edge("Loop", "RF06ref")
g.edge("RF06ref", "Combo")
g.edge("Combo", "Inter")
g.edge("Inter", "Sort")
g.edge("Sort", "Top3F")
g.edge("Top3F", "Out")
diagrams.append((g, "RF-14_02_buildfull"))

# =============================================================================
# Render todos
# =============================================================================
print(f"Renderizando {len(diagrams)} diagramas...")
for g, name in diagrams:
    out = os.path.join(scratch, name)
    g.format = "svg"
    g.render(out, cleanup=True)
    g.format = "png"
    g.render(out, cleanup=True)
    print(f"  ✓ {name}")

print(f"\nArchivos en {scratch}:")
for f in sorted(os.listdir(scratch)):
    sz = os.path.getsize(os.path.join(scratch, f))
    print(f"  {f}  ({sz:,} bytes)")
