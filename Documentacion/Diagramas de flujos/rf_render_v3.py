"""
RF-06 / RF-12 / RF-13 / RF-14 + Arquitectura v3 — Diagramas de flujo

Genera diagramas para los RFs cerrados en abril 2026:
- RF-06: Optimizador de build de discos (greedy + bonus pass)
- RF-12: Optimizador team-aware (lookups + catalogación IA)
- RF-13: Validación lategame (captura + tier list + retro-feedback bayesiano)
- RF-14: Optimizador de armas (scoring contextual + build full)
- Arquitectura v3: visión completa del sistema con todas las capas

Output: SVG + PNG en Documentacion/Diagramas de flujos/
"""

from graphviz import Digraph
import os
import shutil

scratch = "/sessions/blissful-adoring-pasteur/diagramas_scratch_v3"
final_dir = "/sessions/blissful-adoring-pasteur/mnt/Zenless_analitycs/Documentacion/Diagramas de flujos"
os.makedirs(scratch, exist_ok=True)

# ============================================================
# Paleta unificada (consistente con v2)
# ============================================================
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
CONTEXT  = dict(style="filled,rounded", fillcolor="#fef9c3", color="#854d0e", shape="box")
DB       = dict(style="filled,rounded", fillcolor="#f1f5f9", color="#475569", shape="cylinder")

# ============================================================
# RF-06 — Optimizador de build de discos (greedy + bonus pass)
# ============================================================
g06 = Digraph("RF06", format="svg")
g06.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
         label="RF-06 — Optimizador de build por personaje (greedy + bonus pass)",
         labelloc="t", fontsize="14")
g06.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
g06.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")

# Triggers
g06.node("StartManual",  "Trigger manual\n(panel del PJ)", **START)
g06.node("StartAuto",    "Trigger automático\n(tras RF-04 con\nscore ≥ threshold)", **START)
g06.node("Debounce",     "Debounce 2s\npor PJ", **DECISION)

# Carga de inputs
g06.node("LoadPJ",       "Cargar PJ:\nrol, arquetipo,\nthresholds", **PROCESS)
g06.node("LoadInv",      "Cargar inventory_discs\ndisponibles", **DB)
g06.node("LoadActual",   "Cargar build actual\n(agent_discs)", **DB)
g06.node("LoadPrefs",    "Cargar substat\npreferences\ndel PJ", **DB)

# Greedy por slot
g06.node("GreedyLoop",   "Para cada slot 1-6:", **PROCESS)
g06.node("ScoreLocal",   "Score local de cada\ncandidato\n(scoring engine)", **EVAL)
g06.node("TopK",         "Top-K candidatos\npor slot\n(K=8)", **EVAL)

# Bonus pass
g06.node("BonusPass",    "Bonus pass —\nenumerar combinaciones\nde set bonus", **EVAL)
g06.node("Combo4p2p",   "Probar 4pc + 2pc\n(set primario\n+ secundario)", **PROCESS)
g06.node("Combo222",    "Probar 2+2+2\n(stats puros)", **PROCESS)
g06.node("Combo33",     "Probar 3+3\n(casos especiales)", **PROCESS)
g06.node("ScoreFull",   "Score conjunto\n(slots + bonus set\n+ thresholds)", **EVAL)

# Comparación + swaps
g06.node("DeltaActual", "Delta vs build\nactual del PJ", **PROCESS)
g06.node("CheckSwap",   "¿Discos vienen\nde otros PJs?", **DECISION)
g06.node("SwapDelta",   "Calcular delta dual:\nlo que pierde origen,\nlo que gana destino", **EVAL)

# Output
g06.node("Top3",        "Top 3 builds\nrankeadas", **RECO)
g06.node("Persist",     "INSERT en\noptimizer_pending_actions\n(estado=TODO)", **DB)
g06.node("NotifyUI",    "Emitir evento\nUI (RF-11)", **TERMINAL)

# Edges
g06.edge("StartManual", "Debounce")
g06.edge("StartAuto",   "Debounce")
g06.edge("Debounce",    "LoadPJ", label="OK")
g06.edge("Debounce",    "NotifyUI", label="suprimido", style="dashed", color="#9ca3af")

g06.edge("LoadPJ", "LoadInv")
g06.edge("LoadInv", "LoadActual")
g06.edge("LoadActual", "LoadPrefs")
g06.edge("LoadPrefs", "GreedyLoop")

g06.edge("GreedyLoop", "ScoreLocal")
g06.edge("ScoreLocal", "TopK")
g06.edge("TopK", "BonusPass")

g06.edge("BonusPass", "Combo4p2p")
g06.edge("BonusPass", "Combo222")
g06.edge("BonusPass", "Combo33")
g06.edge("Combo4p2p", "ScoreFull")
g06.edge("Combo222", "ScoreFull")
g06.edge("Combo33", "ScoreFull")

g06.edge("ScoreFull", "DeltaActual")
g06.edge("DeltaActual", "CheckSwap")
g06.edge("CheckSwap", "SwapDelta", label="sí")
g06.edge("CheckSwap", "Top3", label="no")
g06.edge("SwapDelta", "Top3")

g06.edge("Top3", "Persist")
g06.edge("Persist", "NotifyUI")

# ============================================================
# RF-12 — Optimizador team-aware (lookup + catalogación IA)
# ============================================================
g12 = Digraph("RF12", format="svg")
g12.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
         label="RF-12 — Optimizador team-aware (3 capas + catalogación IA)",
         labelloc="t", fontsize="14")
g12.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
g12.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")

# Flujo runtime — determinista
with g12.subgraph(name="cluster_runtime") as r:
    r.attr(label="Flujo RUNTIME (determinista, lookup-only)",
           style="rounded", color="#0369a1", fontcolor="#0369a1", fontsize="11")
    r.node("RTStart",    "Usuario abre optimizador\ncon team_context\n[pj, comp1, comp2]", **START)
    r.node("LookupSyn",  "Lookup team_synergies\npara pares\n(pj,comp1) y (pj,comp2)", **DB)
    r.node("CapaA",      "CAPA A —\nOverride de pesos\nde substats", **CONTEXT)
    r.node("PonderaConf","Si dos pares overridean\nmisma stat: ponderar\npor confianza", **PROCESS)
    r.node("CapaB",      "CAPA B —\nOverride de set\nrecomendado\n(si confianza ≥ 0.7)", **CONTEXT)
    r.node("CapaC",      "CAPA C — opcional\nLookup\nteam_compositions\ntop-N por pj_principal", **CONTEXT)
    r.node("CallRF06",   "Invocar RF-06\ncon pesos/set\najustados", **PROCESS)
    r.node("OutputRT",   "Top 3 builds\n+ justificación\nde overrides", **RECO)

g12.edge("RTStart",    "LookupSyn")
g12.edge("LookupSyn",  "CapaA")
g12.edge("CapaA",      "PonderaConf")
g12.edge("PonderaConf","CapaB")
g12.edge("CapaB",      "CapaC")
g12.edge("CapaC",      "CallRF06")
g12.edge("CallRF06",   "OutputRT")

# Flujo de catalogación — IA
with g12.subgraph(name="cluster_catalog") as c:
    c.attr(label="Flujo CATALOGACIÓN (offline, Claude API)",
           style="rounded", color="#9d174d", fontcolor="#9d174d", fontsize="11")
    c.node("CatStart",     "Trigger:\non-demand /\nPJ nuevo (RF-04) /\nset nuevo", **START)
    c.node("CheckCap",     "¿Cap de costo\nmensual\nexcedido?", **DECISION)
    c.node("Pause",        "Pausar cola\n+ notificar", **ALERT)
    c.node("EnqueueBatch", "Encolar lote\n(reusa prompt cache)", **PROCESS)
    c.node("CallSonnet",   "Claude sonnet:\nteam_synergy_pair\n(990 pares)", **AI)
    c.node("CallOpus",     "Claude opus:\nteam_composition_topN\n(45 PJs × top-5)", **AI)
    c.node("Validate",     "Validar response JSON\n+ schema", **EVAL)
    c.node("InsertSyn",    "INSERT/UPDATE\nteam_synergies", **DB)
    c.node("InsertComp",   "INSERT/UPDATE\nteam_compositions", **DB)
    c.node("AuditRun",     "INSERT en\nai_catalog_runs\n(tokens, costo, ms)", **DB)
    c.node("RecalcConf",   "Marcar pares\ncatalogados como\nconfianza inicial", **PROCESS)

g12.edge("CatStart",    "CheckCap")
g12.edge("CheckCap",    "Pause", label="sí")
g12.edge("CheckCap",    "EnqueueBatch", label="no")
g12.edge("EnqueueBatch","CallSonnet")
g12.edge("EnqueueBatch","CallOpus")
g12.edge("CallSonnet",  "Validate")
g12.edge("CallOpus",    "Validate")
g12.edge("Validate",    "InsertSyn")
g12.edge("Validate",    "InsertComp")
g12.edge("InsertSyn",   "AuditRun")
g12.edge("InsertComp",  "AuditRun")
g12.edge("AuditRun",    "RecalcConf")

# Conexión runtime ↔ catalogación
g12.edge("RecalcConf", "LookupSyn", label="alimenta", style="dashed", color="#9d174d")

# ============================================================
# RF-13 — Validación lategame + tier list + retro-feedback
# ============================================================
g13 = Digraph("RF13", format="svg")
g13.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
         label="RF-13 — Validación lategame + tier list personal + retro-feedback bayesiano",
         labelloc="t", fontsize="14")
g13.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
g13.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")

# Flujo de captura manual
with g13.subgraph(name="cluster_capture") as c:
    c.attr(label="CAPTURA — manual, hotkey F11",
           style="rounded", color="#d97706", fontcolor="#d97706", fontsize="11")
    c.node("EndRun",       "Usuario termina\nrun Shiyu/DA", **START)
    c.node("HotkeyF11",    "Hotkey F11", **TRIGGER)
    c.node("ShotResume",   "Capturar pantalla\nresumen\n(estrellas, tiempo,\nequipo)", **PROCESS)
    c.node("UserNavBD",    "Toast pide:\n'Navegar a\nBattle Stats'", **PROCESS)
    c.node("ShotBD",       "Capturar pantalla\nBattle Stats\n(breakdown DMG)", **PROCESS)
    c.node("OCRHybrid",    "OCR híbrido\n(Tesseract texto +\nPaddleOCR números)", **EVAL)
    c.node("ValidConsist", "Validar consistencia:\n• ΣDMG% ≈ 100\n• PJs match roster\n• ciclo activo", **DECISION)
    c.node("ManualCorr",   "Modal de\ncorrección manual", **ALERT)
    c.node("InsertRun",    "INSERT lategame_runs\n+ lategame_run_damage", **DB)
    c.node("ToastConfirm", "Toast confirma\nrun registrado", **TERMINAL)

g13.edge("EndRun",       "HotkeyF11")
g13.edge("HotkeyF11",    "ShotResume")
g13.edge("ShotResume",   "UserNavBD")
g13.edge("UserNavBD",    "ShotBD")
g13.edge("ShotBD",       "OCRHybrid")
g13.edge("OCRHybrid",    "ValidConsist")
g13.edge("ValidConsist", "ManualCorr", label="falla")
g13.edge("ValidConsist", "InsertRun",  label="ok")
g13.edge("ManualCorr",   "InsertRun")
g13.edge("InsertRun",    "ToastConfirm")

# Flujo de tier list
with g13.subgraph(name="cluster_tierlist") as t:
    t.attr(label="TIER LIST — recálculo (N=3 runs / on-demand / semanal)",
           style="rounded", color="#0e7490", fontcolor="#0e7490", fontsize="11")
    t.node("TierTrigger",   "¿Trigger?\nN=3 nuevos /\non-demand /\nsemanal D03:00", **DECISION)
    t.node("NewSnapshot",   "Generar nuevo\nsnapshot_id\n(atómico)", **PROCESS)
    t.node("AggMetrics",    "Para cada\n(pj, contenido):\nagregar K=20 runs", **EVAL)
    t.node("CalcScore",     "Calcular score\nnormalizado\n(rate3★ 0.45 +\nwin 0.20 + dmg 0.20\n+ tiempo 0.15)", **EVAL)
    t.node("AssignBucket",  "Asignar tier\npor buckets fijos\nS+/S/A/B/C/D", **EVAL)
    t.node("LookupPrydwen", "Lookup\nprydwen_tier_snapshots\nmás reciente", **DB)
    t.node("CalcDelta",     "Calcular delta\nvs Prydwen", **PROCESS)
    t.node("GenJustif",     "Generar justificación\ntextual\n(plantilla por delta)", **PROCESS)
    t.node("InsertTier",    "INSERT\ntier_list_personal\n(snapshot_id)", **DB)
    t.node("NotifyTier",    "Notificar UI:\n'tier list recalculada'", **TERMINAL)

g13.edge("ToastConfirm", "TierTrigger", label="cuenta runs", style="dashed")
g13.edge("TierTrigger",  "NewSnapshot", label="dispara")
g13.edge("NewSnapshot",  "AggMetrics")
g13.edge("AggMetrics",   "CalcScore")
g13.edge("CalcScore",    "AssignBucket")
g13.edge("AssignBucket", "LookupPrydwen")
g13.edge("LookupPrydwen","CalcDelta")
g13.edge("CalcDelta",    "GenJustif")
g13.edge("GenJustif",    "InsertTier")
g13.edge("InsertTier",   "NotifyTier")

# Flujo retro-feedback bayesiano
with g13.subgraph(name="cluster_bayes") as b:
    b.attr(label="RETRO-FEEDBACK BAYESIANO (loop con RF-12)",
           style="rounded", color="#6b21a8", fontcolor="#6b21a8", fontsize="11")
    b.node("CheckSyn",    "Run involucra\npar de team_synergies?", **DECISION)
    b.node("AccumEv",     "Acumular evidencia\npor par\n(últimos 90d)", **PROCESS)
    b.node("EnoughEv",    "≥ 3 runs\nde evidencia?", **DECISION)
    b.node("CalcLikely",  "Likelihood =\nrate_3★_obs / 0.75\n(cap 1.5)", **BAYES)
    b.node("CalcPrior",   "Peso prior =\n1 / (1 + 0.3·N)", **BAYES)
    b.node("CalcPost",    "Confianza_post =\nprior·conf_ai +\n(1−prior)·likelihood", **BAYES)
    b.node("CheckCong",   "Sinergia\ncongelada por\nuser?", **DECISION)
    b.node("UpdateConf",  "UPDATE\nteam_synergies.confianza\n+ INSERT en\nteam_synergy_adjustments", **DB)
    b.node("NotifyAdj",   "Badge ±RF-13\nen panel Equipos", **TERMINAL)

g13.edge("InsertRun", "CheckSyn", label="trigger lookup", style="dashed")
g13.edge("CheckSyn",  "AccumEv",    label="sí")
g13.edge("CheckSyn",  "NotifyTier", label="no",  style="dashed", color="#9ca3af")
g13.edge("AccumEv",   "EnoughEv")
g13.edge("EnoughEv",  "NotifyTier", label="no",  style="dashed", color="#9ca3af")
g13.edge("EnoughEv",  "CalcLikely", label="sí")
g13.edge("CalcLikely","CalcPrior")
g13.edge("CalcPrior", "CalcPost")
g13.edge("CalcPost",  "CheckCong")
g13.edge("CheckCong", "UpdateConf",  label="no")
g13.edge("CheckCong", "NotifyTier",  label="sí (skip)", style="dashed", color="#9ca3af")
g13.edge("UpdateConf","NotifyAdj")

# ============================================================
# RF-14 — Optimizador de armas (scoring contextual + build full)
# ============================================================
g14 = Digraph("RF14", format="svg")
g14.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
         label="RF-14 — Optimizador de armas (scoring contextual por contenido + build full)",
         labelloc="t", fontsize="14")
g14.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
g14.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")

# Inputs
g14.node("StartW",      "Usuario abre\noptimizador de armas\npara PJ + contenido", **START)
g14.node("CheckCache",  "¿Existe en\nweapon_evaluations\n(snapshot vigente)?", **DECISION)
g14.node("LookupCache", "Lookup directo\n(< 5 ms)", **DB)

# Carga de inputs
g14.node("LoadPJW",     "Cargar PJ:\nrol, stats efectivos,\nawakenings activos", **PROCESS)
g14.node("LoadProfile", "Cargar\ncontent_profiles\n(TTL boss, uptime\nHP>50%, etc.)", **DB)
g14.node("LoadSyn",     "Cargar\npj_weapon_synergy\nseed", **DB)
g14.node("LoadCatalog", "Cargar 49 W-Engines\n(catálogo) +\ninventory_weapons\n(disponibles)", **DB)

# Loop de scoring por arma
g14.node("WLoop",       "Para cada arma:", **PROCESS)
g14.node("ScoreATK",    "score_atk_base\n+ score_stat2\n(lineal)", **EVAL)
g14.node("PassivesLoop","Para cada pasiva en\nweapon_passives_structured:", **PROCESS)
g14.node("CalcUptime",  "Uptime contextual\nsegún trigger_tipo +\ncontent_profile", **CONTEXT)
g14.node("StatImpact",  "stat_impact_for_pj\n(pesos por rol)", **EVAL)
g14.node("AccumPassive","Acumular\nscore_pasivas\n(× uptime)", **EVAL)
g14.node("ScoreText",   "score_pasiva_textual\n(override manual)", **EVAL)
g14.node("ScoreSyn",    "score_synergy_pj\n(habilidades core)", **EVAL)
g14.node("Total",       "Score total =\nATK 25 + stat2 15 +\npasivas 40 + texto 10\n+ synergy 10", **EVAL)

# Comparación + output
g14.node("LookupPW",    "Lookup\nprydwen_weapon_\nsnapshots", **DB)
g14.node("DeltaPW",     "Calcular delta\nvs Prydwen", **PROCESS)
g14.node("RankIdeal",   "Ranking IDEAL\n(catálogo 49)", **RECO)
g14.node("RankAvail",   "Ranking DISPONIBLE\n(inventario)", **RECO)
g14.node("InsertEval",  "INSERT\nweapon_evaluations\n(snapshot)", **DB)

# Build full opcional
g14.node("BuildFullQ",  "¿Modo\nBuild Full\nRF-06+RF-14?", **DECISION)
g14.node("Top3Armas",   "Tomar top 3 armas", **PROCESS)
g14.node("CallRF06W",   "Para cada arma,\ninvocar RF-06\n(top 3 builds discos)", **PROCESS)
g14.node("ScoreCombo",  "Score conjunto\n(arma + 6 discos)\ncon interacciones\n(CRIT cap, thresholds,\nER awakenings)", **EVAL)
g14.node("Top3Combos",  "Top 3 combinaciones\nfull (arma + discos)", **RECO)

# Output
g14.node("UIOutput",    "Output → UI:\n4 subpestañas\n(Ranking PJ /\nBuild Full / Catálogo /\nComparativo Prydwen)", **TERMINAL)

# Edges
g14.edge("StartW", "CheckCache")
g14.edge("CheckCache", "LookupCache", label="sí")
g14.edge("CheckCache", "LoadPJW",     label="no")
g14.edge("LookupCache", "UIOutput")

g14.edge("LoadPJW",     "LoadProfile")
g14.edge("LoadProfile", "LoadSyn")
g14.edge("LoadSyn",     "LoadCatalog")
g14.edge("LoadCatalog", "WLoop")

g14.edge("WLoop", "ScoreATK")
g14.edge("ScoreATK", "PassivesLoop")
g14.edge("PassivesLoop", "CalcUptime")
g14.edge("CalcUptime", "StatImpact")
g14.edge("StatImpact", "AccumPassive")
g14.edge("AccumPassive", "ScoreText")
g14.edge("ScoreText", "ScoreSyn")
g14.edge("ScoreSyn", "Total")

g14.edge("Total", "LookupPW")
g14.edge("LookupPW", "DeltaPW")
g14.edge("DeltaPW", "RankIdeal")
g14.edge("DeltaPW", "RankAvail")
g14.edge("RankIdeal", "InsertEval")
g14.edge("RankAvail", "InsertEval")

g14.edge("InsertEval", "BuildFullQ")
g14.edge("BuildFullQ", "Top3Armas",  label="sí")
g14.edge("BuildFullQ", "UIOutput",   label="no")
g14.edge("Top3Armas", "CallRF06W")
g14.edge("CallRF06W", "ScoreCombo")
g14.edge("ScoreCombo", "Top3Combos")
g14.edge("Top3Combos", "UIOutput")

# ============================================================
# Arquitectura v3 — Visión completa del sistema
# ============================================================
arch = Digraph("Arch_v3", format="svg")
arch.attr(rankdir="TB", bgcolor="white", fontname="Helvetica",
          label="Arquitectura v3 — Sistema completo (RF-04/05/06/09/11/12/13/14 cerrados)",
          labelloc="t", fontsize="14")
arch.attr("node", fontname="Helvetica", fontsize="10", margin="0.15,0.08")
arch.attr("edge", fontname="Helvetica", fontsize="9", color="#374151")

# Capa: Captura
with arch.subgraph(name="cluster_captura") as c:
    c.attr(label="CAPA 1 — CAPTURA",
           style="rounded", color="#d97706", fontcolor="#d97706", fontsize="11")
    c.node("CapZZZ",   "ZZZ corriendo\n(monitor mss)", **TRIGGER)
    c.node("CapAuto",  "Polling adaptativo\nRF-04/RF-05\n(500ms / 2-5s)", **PROCESS)
    c.node("CapF11",   "Hotkey F11\nRF-13 lategame", **TRIGGER)
    c.node("CapF8",    "Hotkey F8\nmanual", **TRIGGER)
    c.node("OCR",      "OCR híbrido\nRF-09\n(Tesseract+Paddle)", **EVAL)

# Capa: Scoring
with arch.subgraph(name="cluster_scoring") as s:
    s.attr(label="CAPA 2 — SCORING (engine compartido)",
           style="rounded", color="#0e7490", fontcolor="#0e7490", fontsize="11")
    s.node("ArchMatch","Match arquetipo\nprimario/secundario", **EVAL)
    s.node("ScoreEng", "Scoring engine\npos×rolls −\nneg×rolls + bonuses", **EVAL)
    s.node("Reco",     "Recomendación:\nequipar/mejorar/\nreservar/descartar", **RECO)

# Capa: Optimización
with arch.subgraph(name="cluster_optim") as o:
    o.attr(label="CAPA 3 — OPTIMIZACIÓN",
           style="rounded", color="#0369a1", fontcolor="#0369a1", fontsize="11")
    o.node("Opt06",    "RF-06\nOptimizador\nde discos\n(greedy + bonus pass)", **PROCESS)
    o.node("Opt12",    "RF-12\nOptimizador\nteam-aware\n(3 capas)", **PROCESS)
    o.node("Opt14",    "RF-14\nOptimizador\nde armas\n(scoring contextual)", **PROCESS)
    o.node("BuildFull","Build full\n(arma + 6 discos\nconjunto)", **RECO)

# Capa: Validación + IA
with arch.subgraph(name="cluster_valid") as v:
    v.attr(label="CAPA 4 — VALIDACIÓN + IA",
           style="rounded", color="#9d174d", fontcolor="#9d174d", fontsize="11")
    v.node("AICatalog","Claude API\ncatalogadora\n(sonnet/opus)", **AI)
    v.node("TierList", "Tier list calibrada\nvs Prydwen\n(buckets fijos)", **EVAL)
    v.node("Bayes",    "Retro-feedback\nbayesiano\nsobre confianza", **BAYES)

# Capa: UI
with arch.subgraph(name="cluster_ui") as u:
    u.attr(label="CAPA 5 — UI (RF-11 standalone .exe)",
           style="rounded", color="#7c3aed", fontcolor="#7c3aed", fontsize="11")
    u.node("Toast",    "Toast flotante\n(< 500ms)", **RECO)
    u.node("Panel",    "Panel detalle\n(5 pestañas base)", **PROCESS)
    u.node("Lategame", "Pestaña\nLategame", **PROCESS)
    u.node("Teams",    "Pestaña\nEquipos", **PROCESS)
    u.node("Weapons",  "Pestaña\nArmas", **PROCESS)
    u.node("Tray",     "System tray", **TERMINAL)

# Capa: Persistencia
with arch.subgraph(name="cluster_db") as d:
    d.attr(label="PERSISTENCIA — danibod_zzz_v2.db (5 migraciones)",
           style="rounded", color="#475569", fontcolor="#475569", fontsize="11")
    d.node("DBCore",   "agents · weapons ·\ndisc_sets · agent_discs ·\ninventory_discs ·\ninventory_weapons", **DB)
    d.node("DBScore",  "Mig 01 — arquetipos +\nthresholds +\ninventory_disc_evaluations", **DB)
    d.node("DBOptim",  "Mig 02 —\noptimizer_pending_actions", **DB)
    d.node("DBTeam",   "Mig 03 — team_synergies +\nteam_compositions +\nai_catalog_runs", **DB)
    d.node("DBLG",     "Mig 04 — enemies +\nlategame_runs + tier_list +\nprydwen_snapshots +\nteam_synergy_adjustments", **DB)
    d.node("DBWeap",   "Mig 05 —\nweapon_passives_structured +\ncontent_profiles +\nweapon_evaluations +\npj_weapon_synergy", **DB)

# Edges - Captura → Scoring → Optimización
arch.edge("CapZZZ",   "CapAuto")
arch.edge("CapAuto",  "OCR")
arch.edge("CapF8",    "OCR")
arch.edge("CapF11",   "OCR")
arch.edge("OCR",      "ArchMatch")
arch.edge("ArchMatch","ScoreEng")
arch.edge("ScoreEng", "Reco")

arch.edge("ScoreEng", "Opt06")
arch.edge("Opt06",    "Opt12", label="invoca")
arch.edge("Opt06",    "BuildFull")
arch.edge("Opt14",    "BuildFull")
arch.edge("Opt12",    "Opt14", label="ajusta uptime")

# Validación + IA
arch.edge("AICatalog","Opt12", label="puebla\nteam_synergies", style="dashed", color="#9d174d")
arch.edge("CapF11",   "TierList", label="runs", style="dashed", color="#0e7490")
arch.edge("TierList", "Bayes")
arch.edge("Bayes",    "Opt12", label="ajusta\nconfianza", style="dashed", color="#6b21a8")
arch.edge("TierList", "Opt14", label="recalibra\ncontent_profiles", style="dashed", color="#0e7490")

# UI
arch.edge("Reco",     "Toast")
arch.edge("Reco",     "Panel")
arch.edge("BuildFull","Weapons")
arch.edge("Opt12",    "Teams")
arch.edge("TierList", "Lategame")
arch.edge("Toast",    "Tray")
arch.edge("Panel",    "Tray")

# Persistencia
arch.edge("OCR",     "DBCore",  style="dotted", color="#475569")
arch.edge("Reco",    "DBScore", style="dotted", color="#475569")
arch.edge("Opt06",   "DBOptim", style="dotted", color="#475569")
arch.edge("Opt12",   "DBTeam",  style="dotted", color="#475569")
arch.edge("TierList","DBLG",    style="dotted", color="#475569")
arch.edge("Opt14",   "DBWeap",  style="dotted", color="#475569")
arch.edge("AICatalog","DBTeam", style="dotted", color="#475569")

# ============================================================
# Render: SVG + PNG para cada diagrama
# ============================================================
diagrams = [
    (g06,  "RF-06_v1_optimizador_build"),
    (g12,  "RF-12_v1_optimizador_equipos"),
    (g13,  "RF-13_v1_lategame_validation"),
    (g14,  "RF-14_v1_optimizador_armas"),
    (arch, "Arquitectura_v3_completa"),
]

for g, name in diagrams:
    out_svg = os.path.join(scratch, name)
    g.format = "svg"
    g.render(out_svg, cleanup=True)
    g.format = "png"
    g.render(out_svg, cleanup=True)
    print(f"Generado: {name}.svg + .png")

print("\nArchivos en scratch:")
for f in sorted(os.listdir(scratch)):
    path = os.path.join(scratch, f)
    print(f"  {f} ({os.path.getsize(path)} bytes)")
