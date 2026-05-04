"""
Modelo Relacional (MR) — Diagrama ER de danibod_zzz_v2.db

Genera un diagrama ER completo de las ~30 tablas de la base, agrupadas por
capa funcional, con FKs explícitas. Usa labels HTML de graphviz para mostrar
campos clave.

Output:
- Modelo_Relacional_v1.svg
- Modelo_Relacional_v1.png

Convenciones:
  PK  = clave primaria (negrita)
  FK  = clave foránea (italic + flecha hacia tabla referenciada)
  *   = NOT NULL relevante
  ✓   = UNIQUE
"""

from graphviz import Digraph
import os

scratch = "/sessions/blissful-adoring-pasteur/mr_scratch"
os.makedirs(scratch, exist_ok=True)

g = Digraph("MR", format="svg", node_attr={"shape": "plain", "fontname": "Helvetica"})
g.attr(rankdir="LR", bgcolor="white", fontname="Helvetica",
       label="Modelo Relacional — danibod_zzz_v2.db (post-migraciones 01-05)\n"
             "30 tablas agrupadas por capa · FKs explícitas",
       labelloc="t", fontsize="14",
       splines="spline", nodesep="0.5", ranksep="0.8")
g.attr("edge", fontname="Helvetica", fontsize="9", color="#475569", arrowsize="0.7")

# Helper para tablas con label HTML (sin port-names para evitar conflictos)
def esc(s):
    """Escape caracteres problemáticos para HTML labels de graphviz."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace("[", "&#91;")
             .replace("]", "&#93;"))

def tbl(name, fields, color="#0369a1", bg="#e0f2fe"):
    """fields = list of (icon, name, type) tuples"""
    def render_row(icon, fname, ftype):
        # Evitar font-tags vacíos
        icon_html = f'<font color="#475569">{esc(icon)}</font> ' if icon else ''
        type_html = f' <font color="#94a3b8" point-size="8">{esc(ftype)}</font>' if ftype else ''
        return f'<tr><td align="left">{icon_html}<b>{esc(fname)}</b>{type_html}</td></tr>'

    rows = "".join(render_row(*f) for f in fields)
    label = (
        f'<<table border="0" cellborder="0" cellspacing="0" cellpadding="3" '
        f'bgcolor="{bg}" style="rounded">'
        f'<tr><td bgcolor="{color}"><font color="white"><b>{name}</b></font></td></tr>'
        f'{rows}</table>>'
    )
    g.node(name, label=label, shape="plain")

# Colores por capa
C_CATALOG  = ("#7c3aed", "#f3e8ff")  # purple
C_INVENT   = ("#0369a1", "#e0f2fe")  # blue
C_THRESH   = ("#0e7490", "#cffafe")  # cyan
C_SCORING  = ("#15803d", "#dcfce7")  # green
C_OPTIM    = ("#a16207", "#fef3c7")  # amber
C_TEAM     = ("#9d174d", "#fbcfe8")  # pink
C_LATEGAME = ("#6b21a8", "#e9d5ff")  # violet
C_WEAPON   = ("#b91c1c", "#fee2e2")  # red

# ========= Cluster 1: Catálogos del juego =========
with g.subgraph(name="cluster_cat") as c:
    c.attr(label="CATÁLOGOS DEL JUEGO", style="rounded", color=C_CATALOG[0],
           fontcolor=C_CATALOG[0], fontsize="11")
    tbl("agents", [
        ("PK", "id", "INTEGER"),
        ("",   "nombre", "TEXT"),
        ("",   "rango", "TEXT (S/A)"),
        ("",   "elemento", "TEXT"),
        ("",   "rol", "TEXT"),
        ("",   "faccion", "TEXT"),
        ("",   "nivel + mindscape", ""),
        ("",   "stats efectivos…", "(12 cols)"),
        ("FK", "weapon_id", "→ weapons"),
        ("FK", "set_4p_id", "→ disc_sets"),
        ("FK", "set_2p_id", "→ disc_sets"),
    ], *C_CATALOG)

    tbl("weapons", [
        ("PK", "id", "INTEGER"),
        ("",   "nombre + nombre_en", ""),
        ("",   "rareza, tipo_especialidad", ""),
        ("",   "atk_base, stat_secundario", ""),
        ("",   "pasiva_tipo", "TEXT"),
        ("",   "pasiva_condicion/_valor", ""),
        ("",   "pasiva_descripcion", ""),
        ("+",  "pasiva_modelada", "(mig 05)"),
        ("+",  "sensibilidad_contexto", "(mig 05)"),
    ], *C_CATALOG)

    tbl("disc_sets", [
        ("PK", "id", "INTEGER"),
        ("",   "nombre + nombre_en", ""),
        ("",   "bonus_2p_stat/_valor", ""),
        ("",   "bonus_4p_desc", "TEXT"),
    ], *C_CATALOG)

    tbl("agent_awakenings", [
        ("PK", "id", "INTEGER"),
        ("FK", "agente_id", "→ agents"),
        ("",   "nivel (1-6)", ""),
        ("",   "nombre, descripcion", ""),
        ("",   "tipo_efecto, activo", ""),
        ("",   "version_juego", ""),
    ], *C_CATALOG)

# ========= Cluster 2: Inventarios =========
with g.subgraph(name="cluster_inv") as c:
    c.attr(label="INVENTARIOS", style="rounded", color=C_INVENT[0],
           fontcolor=C_INVENT[0], fontsize="11")
    tbl("agent_discs", [
        ("PK", "id", "INTEGER"),
        ("FK", "agente_id", "→ agents"),
        ("",   "slot (1-6)", ""),
        ("FK", "set_id", "→ disc_sets"),
        ("",   "nivel, main_stat, main_valor", ""),
        ("",   "sub1..sub4 + val + _up", ""),
    ], *C_INVENT)

    tbl("inventory_discs", [
        ("PK", "id", "INTEGER"),
        ("FK", "set_id", "→ disc_sets"),
        ("",   "slot, main_stat, main_valor", ""),
        ("",   "sub1..sub4, val, rolls", ""),
        ("",   "nivel", ""),
        ("FK", "agente_asignado", "→ agents"),
        ("",   "equipado, descartado", ""),
        ("",   "score_evaluacion", ""),
        ("",   "agentes_compatibles", "JSON"),
    ], *C_INVENT)

    tbl("inventory_weapons", [
        ("PK", "id", "INTEGER"),
        ("FK", "weapon_id", "→ weapons"),
        ("",   "nivel, refinamiento", ""),
        ("FK", "agente_asignado", "→ agents"),
        ("",   "equipado", ""),
    ], *C_INVENT)

# ========= Cluster 3: Thresholds + preferences =========
with g.subgraph(name="cluster_thresh") as c:
    c.attr(label="THRESHOLDS + PREFERENCIAS (mig 01)", style="rounded",
           color=C_THRESH[0], fontcolor=C_THRESH[0], fontsize="11")
    tbl("agent_thresholds", [
        ("PK", "id", "INTEGER"),
        ("FK", "agente_id", "→ agents"),
        ("",   "stat", "TEXT"),
        ("",   "valor_minimo, valor_optimo", ""),
        ("",   "valor_maximo", ""),
        ("",   "descripcion, fuente", ""),
    ], *C_THRESH)

    tbl("agent_score_thresholds", [
        ("PK", "agente_id", "→ agents"),
        ("",   "threshold_equip", "REAL=0.75"),
        ("",   "threshold_upgrade", "REAL=0.50"),
        ("",   "fuente, actualizado", ""),
    ], *C_THRESH)

    tbl("agent_substat_preferences", [
        ("PK", "agente_id+substat", ""),
        ("FK", "agente_id", "→ agents"),
        ("",   "substat", "TEXT"),
        ("",   "peso", "REAL [-1,+1]"),
        ("",   "fuente", ""),
    ], *C_THRESH)

# ========= Cluster 4: Arquetipos + Scoring (mig 01) =========
with g.subgraph(name="cluster_score") as c:
    c.attr(label="ARQUETIPOS + SCORING (mig 01)", style="rounded",
           color=C_SCORING[0], fontcolor=C_SCORING[0], fontsize="11")
    tbl("disc_archetypes", [
        ("PK", "id", "INTEGER"),
        ("✓",  "code", "TEXT"),
        ("",   "nombre, descripcion", ""),
        ("",   "mains_4/_5/_6", "JSON"),
        ("",   "substats_positivos", "JSON"),
        ("",   "substats_perjudiciales", "JSON"),
        ("",   "threshold_stock", "REAL=0.7"),
    ], *C_SCORING)

    tbl("disc_set_archetype", [
        ("PK", "set_id+archetype_id", ""),
        ("FK", "set_id", "→ disc_sets"),
        ("FK", "archetype_id", "→ disc_archetypes"),
        ("",   "prioridad", "1=primario, 2=sec"),
    ], *C_SCORING)

    tbl("inventory_disc_evaluations", [
        ("PK", "id", "INTEGER"),
        ("FK", "inventory_disc_id", "→ inventory_discs"),
        ("",   "fecha", "DATETIME"),
        ("",   "trigger_evento", "TEXT"),
        ("",   "recomendacion, score", ""),
        ("",   "detalle_json", "JSON"),
    ], *C_SCORING)

# ========= Cluster 5: Optimizador (mig 02) =========
with g.subgraph(name="cluster_optim") as c:
    c.attr(label="OPTIMIZADOR DE BUILD (mig 02 — RF-06)", style="rounded",
           color=C_OPTIM[0], fontcolor=C_OPTIM[0], fontsize="11")
    tbl("optimizer_pending_actions", [
        ("PK", "id", "INTEGER"),
        ("FK", "agente_id", "→ agents"),
        ("",   "rank (1-3)", ""),
        ("",   "score_estimado, _actual, delta", ""),
        ("",   "build_json", "JSON"),
        ("",   "set_bonus", "TEXT"),
        ("",   "requiere_swaps", "JSON"),
        ("",   "estado", "TODO/APLICADO/..."),
        ("",   "fuente_trigger, fechas", ""),
    ], *C_OPTIM)

# ========= Cluster 6: Team-aware (mig 03 + flag mig 04) =========
with g.subgraph(name="cluster_team") as c:
    c.attr(label="TEAM-AWARE (mig 03 — RF-12)", style="rounded",
           color=C_TEAM[0], fontcolor=C_TEAM[0], fontsize="11")
    tbl("team_synergies", [
        ("PK", "id", "INTEGER"),
        ("FK", "pj_a_id", "→ agents"),
        ("FK", "pj_b_id", "→ agents"),
        ("✓",  "(pj_a, pj_b) UNIQUE", "+ pj_a<pj_b"),
        ("",   "sinergia_existe (0/1)", ""),
        ("",   "tipo (9 categorías)", ""),
        ("FK", "set_recomendado_pj_a/b", "→ disc_sets"),
        ("",   "pesos_substat_override_*", "JSON"),
        ("",   "buff_descripcion, confianza", ""),
        ("",   "fuente, modelo_version", ""),
        ("+",  "congelado (0/1)", "(mig 04)"),
    ], *C_TEAM)

    tbl("team_compositions", [
        ("PK", "id", "INTEGER"),
        ("FK", "pj_principal_id", "→ agents"),
        ("FK", "pj_companion_1_id", "→ agents"),
        ("FK", "pj_companion_2_id", "→ agents"),
        ("",   "score_composicion (0-100)", ""),
        ("",   "rank_para_principal", ""),
        ("",   "contenido_optimo", ""),
        ("",   "justificacion", ""),
        ("",   "sinergias_activadas", "JSON"),
        ("",   "requiere_stunner", ""),
        ("",   "flag_anti_shill", ""),
    ], *C_TEAM)

    tbl("ai_catalog_runs", [
        ("PK", "id", "INTEGER"),
        ("",   "operacion (7 tipos)", ""),
        ("",   "modelo", "claude-*-4-6"),
        ("",   "pj_ids, weapon_ids", "JSON"),
        ("",   "prompt_hash", ""),
        ("",   "tokens_input/_cached/_output", ""),
        ("",   "costo_usd, duracion_ms", ""),
        ("",   "exito, error_msg", ""),
        ("",   "response_json", "(opcional)"),
    ], *C_TEAM)

# ========= Cluster 7: Lategame (mig 04) =========
with g.subgraph(name="cluster_lg") as c:
    c.attr(label="VALIDACIÓN LATEGAME (mig 04 — RF-13)", style="rounded",
           color=C_LATEGAME[0], fontcolor=C_LATEGAME[0], fontsize="11")
    tbl("enemies", [
        ("PK", "id", "INTEGER"),
        ("✓",  "nombre_es", ""),
        ("",   "tipo (4 categorías)", ""),
        ("",   "faccion, hp_base, nivel_ref", ""),
        ("",   "escalado_dificultad", "JSON"),
        ("",   "mecanicas_clave, fuente", ""),
    ], *C_LATEGAME)

    tbl("enemy_resistances", [
        ("PK", "id", "INTEGER"),
        ("FK", "enemy_id", "→ enemies"),
        ("",   "elemento (6 valores)", ""),
        ("",   "multiplicador, breakdown", ""),
    ], *C_LATEGAME)

    tbl("shiyu_cycles", [
        ("PK", "id", "INTEGER"),
        ("✓",  "cycle_number", ""),
        ("",   "fecha_inicio/_fin", ""),
        ("",   "frentes (FKs en JSON)", ""),
    ], *C_LATEGAME)

    tbl("da_cycles", [
        ("PK", "id", "INTEGER"),
        ("✓",  "cycle_number", ""),
        ("",   "fecha_inicio/_fin", ""),
        ("",   "entidades (FKs en JSON)", ""),
    ], *C_LATEGAME)

    tbl("lategame_runs", [
        ("PK", "id", "INTEGER"),
        ("",   "fecha, contenido", ""),
        ("",   "cycle_id, frente_o_slot", ""),
        ("FK", "pj_principal_id", "→ agents"),
        ("FK", "pj_companion_1/2_id", "→ agents"),
        ("",   "estrellas, tiempo, score", ""),
        ("",   "completado", ""),
        ("",   "screenshot_*_path", ""),
        ("",   "fuente_captura", ""),
    ], *C_LATEGAME)

    tbl("lategame_run_damage", [
        ("PK", "id", "INTEGER"),
        ("FK", "run_id", "→ lategame_runs"),
        ("FK", "agent_id", "→ agents"),
        ("",   "posicion (1-3)", ""),
        ("",   "dmg_total, dmg_porcentaje", ""),
        ("",   "rol_efectivo", ""),
    ], *C_LATEGAME)

    tbl("tier_list_personal", [
        ("PK", "id", "INTEGER"),
        ("FK", "pj_id", "→ agents"),
        ("",   "contenido (granular)", ""),
        ("",   "tier (S+/S/A/B/C/D)", ""),
        ("",   "score_normalizado", ""),
        ("",   "métricas agregadas (5 cols)", ""),
        ("",   "delta_vs_prydwen", ""),
        ("",   "justificacion", ""),
        ("",   "snapshot_id", ""),
    ], *C_LATEGAME)

    tbl("prydwen_tier_snapshots", [
        ("PK", "id", "INTEGER"),
        ("",   "fecha, contenido", ""),
        ("",   "tier_data", "JSON"),
        ("",   "fuente_url, parser_version", ""),
    ], *C_LATEGAME)

    tbl("team_synergy_adjustments", [
        ("PK", "id", "INTEGER"),
        ("FK", "synergy_id", "→ team_synergies"),
        ("",   "fecha", ""),
        ("",   "confianza_anterior/_nueva", ""),
        ("",   "runs_evidencia", ""),
        ("",   "rate_3star_observado", ""),
        ("",   "motivo", ""),
    ], *C_LATEGAME)

# ========= Cluster 8: Armas (mig 05) =========
with g.subgraph(name="cluster_w") as c:
    c.attr(label="OPTIMIZADOR DE ARMAS (mig 05 — RF-14)", style="rounded",
           color=C_WEAPON[0], fontcolor=C_WEAPON[0], fontsize="11")
    tbl("weapon_passives_structured", [
        ("PK", "id", "INTEGER"),
        ("FK", "weapon_id", "→ weapons"),
        ("",   "trigger_tipo (15 categorías)", ""),
        ("",   "trigger_params", "JSON"),
        ("",   "modifier_stat, value_r1/_r5", ""),
        ("",   "modifier_stack_max, uptime_base", ""),
        ("",   "descripcion_breve", ""),
    ], *C_WEAPON)

    tbl("content_profiles", [
        ("PK", "id", "INTEGER"),
        ("✓",  "contenido", "(4 valores seed)"),
        ("",   "ttl_boss_promedio_s", ""),
        ("",   "hp_uptime_above_50/_30pct", ""),
        ("",   "chain/skills/ulti_por_min", ""),
        ("",   "anomalies/stuns_por_min", ""),
        ("",   "promedio_pjs_off_field", ""),
    ], *C_WEAPON)

    tbl("weapon_evaluations", [
        ("PK", "id", "INTEGER"),
        ("FK", "pj_id", "→ agents"),
        ("FK", "weapon_id", "→ weapons"),
        ("",   "refinamiento (1-5), nivel", ""),
        ("FK", "contenido", "→ content_profiles"),
        ("",   "score_normalizado (0-100)", ""),
        ("",   "score_atk/_stat2/_pasiva*", ""),
        ("",   "score_synergy_pj", ""),
        ("",   "delta_vs_prydwen", ""),
        ("",   "snapshot_id", ""),
    ], *C_WEAPON)

    tbl("prydwen_weapon_snapshots", [
        ("PK", "id", "INTEGER"),
        ("",   "fecha", ""),
        ("FK", "pj_id", "→ agents"),
        ("",   "recomendaciones", "JSON"),
        ("",   "fuente_url, parser_version", ""),
    ], *C_WEAPON)

    tbl("pj_weapon_synergy", [
        ("PK", "id", "INTEGER"),
        ("FK", "pj_id", "→ agents"),
        ("",   "weapon_pasiva_tipo", ""),
        ("",   "bonus [-1, 2]", ""),
        ("",   "razon, fuente", ""),
    ], *C_WEAPON)

# ========= Edges (FKs) — entre tablas, sin ports específicos =========
def fk(src, dst, label=None):
    if label:
        g.edge(src, dst, color="#475569", label=label, fontsize="8", fontcolor="#64748b")
    else:
        g.edge(src, dst, color="#475569")

# Catálogos → agents
fk("agents", "weapons", "weapon_id")
fk("agents", "disc_sets", "set_4p+2p_id")
fk("agent_awakenings", "agents")

# Inventarios
fk("agent_discs", "agents")
fk("agent_discs", "disc_sets")
fk("inventory_discs", "disc_sets")
fk("inventory_discs", "agents")
fk("inventory_weapons", "weapons")
fk("inventory_weapons", "agents")

# Thresholds
fk("agent_thresholds", "agents")
fk("agent_score_thresholds", "agents")
fk("agent_substat_preferences", "agents")

# Scoring
fk("disc_set_archetype", "disc_sets")
fk("disc_set_archetype", "disc_archetypes")
fk("inventory_disc_evaluations", "inventory_discs")

# Optimizador (mig 02)
fk("optimizer_pending_actions", "agents")

# Team-aware (mig 03)
fk("team_synergies", "agents", "pj_a + pj_b")
fk("team_synergies", "disc_sets", "set_rec_pj_a/b")
fk("team_compositions", "agents", "principal + comps")

# Lategame (mig 04)
fk("enemy_resistances", "enemies")
fk("lategame_runs", "agents", "principal + comps")
fk("lategame_run_damage", "lategame_runs")
fk("lategame_run_damage", "agents")
fk("tier_list_personal", "agents")
fk("team_synergy_adjustments", "team_synergies")

# Armas (mig 05)
fk("weapon_passives_structured", "weapons")
fk("weapon_evaluations", "agents")
fk("weapon_evaluations", "weapons")
fk("weapon_evaluations", "content_profiles")
fk("prydwen_weapon_snapshots", "agents")
fk("pj_weapon_synergy", "agents")

# Render SVG + PNG
out_path = os.path.join(scratch, "Modelo_Relacional_v1")
g.format = "svg"
g.render(out_path, cleanup=True)
g.format = "png"
g.render(out_path, cleanup=True)

print("Generado:")
for f in sorted(os.listdir(scratch)):
    sz = os.path.getsize(os.path.join(scratch, f))
    print(f"  {f}  ({sz:,} bytes)")
