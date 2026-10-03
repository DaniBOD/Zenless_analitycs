"""Medir si la app sigue el ritmo del usuario: verdad de tierra de una grabación vs lo que la app vio.

Hito "El ritmo de Daniel" (DIAG y plan del 2026-10-02). Dos mitades, puras y testeables:

- **La verdad** (`eventos_de_verdad`): sale de recorrer TODOS los frames de una grabación sin
  apuro (`tools/verdad_de_sesion.py` llama a `observar_frame` por frame). Qué pantallas hubo y
  cuánto duraron, cuántos discos se marcaron en S11, cuántas tandas se confirmaron, cuántos niveles
  subió S10, cuántos discos distintos mostró el panel del Obtenido.
- **Lo que vio la app** (`kpis_de_log`): sale de las líneas del log de una REPRODUCCIÓN de esa
  grabación contra el loop real (`tools/reproducir_sesion.py`). Son las mismas líneas de "un
  evento, una línea" que se leen en vivo.

`comparar` las cruza y `reporte_md` lo deja escrito en `audit/ritmo/`. La regla de la Fase 1: el
banco sirve sólo si la reproducción del código de hoy reproduce las pérdidas de hoy (~30 % sin
leer en S11, la tanda que no cierra); si no, no mide nada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Pantallas que la app tiene que ver aunque duren poco: modales y confirmaciones.
ESTADOS_BREVES = ("S20", "S23", "S24", "S25")


@dataclass
class ObsFrame:
    """Lo que se ve en UN frame grabado (verdad de tierra, sin votación ni cadencia)."""
    t: float
    estado: str
    contador_s11: int | None = None     # N de "N/300" en S11
    nivel_s10: int | None = None        # nivel del disco en el modal de mejora
    panel_s22: str | None = None        # identidad del disco del panel DETAIL del Obtenido


@dataclass
class Corrida:
    estado: str
    t_ini: float
    t_fin: float

    @property
    def dura(self) -> float:
        return self.t_fin - self.t_ini


@dataclass
class Verdad:
    corridas: list[Corrida] = field(default_factory=list)
    s11_marcados: int = 0               # +1 del contador (lo que la app tendría que leer)
    s11_tandas_confirmadas: int = 0     # S25 seguido de S24 o de la selección vaciada
    s10_niveles: int = 0                # niveles subidos vistos en S10
    s22_discos: int = 0                 # discos distintos mostrados en el panel del Obtenido
    breves: dict[str, int] = field(default_factory=dict)


def corridas(obs: list[ObsFrame]) -> list[Corrida]:
    """Frames consecutivos con el mismo estado → una corrida (desde su primer frame hasta el
    primero del estado siguiente)."""
    out: list[Corrida] = []
    for o in sorted(obs, key=lambda o: o.t):
        if out and out[-1].estado == o.estado:
            continue
        if out:
            out[-1].t_fin = o.t
        out.append(Corrida(o.estado, o.t, o.t))
    if out:
        out[-1].t_fin = max(o.t for o in obs)
    return out


# Un S12 más corto que esto entre dos frames es la transición de la animación, no una pantalla:
# en la grabación del 2026-10-03 aparecen de a 0,12 s entre casi todos los cambios y partían una
# misma visita a S10 en tres (la subida 0→3 no se veía).
PARPADEO_S12_S = 0.5


def sin_parpadeos(obs: list[ObsFrame], max_s: float = PARPADEO_S12_S) -> list[ObsFrame]:
    """Los frames sin las corridas de S12 más cortas que `max_s` (ordenados por t)."""
    obs = sorted(obs, key=lambda o: o.t)
    fuera: set[int] = set()
    i = 0
    while i < len(obs):
        if obs[i].estado != "S12":
            i += 1
            continue
        j = i
        while j + 1 < len(obs) and obs[j + 1].estado == "S12":
            j += 1
        fin = obs[j + 1].t if j + 1 < len(obs) else obs[j].t
        if 0 < i and j + 1 < len(obs) and fin - obs[i].t < max_s:
            fuera.update(range(i, j + 1))
        i = j + 1
    return [o for k, o in enumerate(obs) if k not in fuera]


def eventos_de_verdad(obs: list[ObsFrame]) -> Verdad:
    obs = sin_parpadeos(obs)
    v = Verdad(corridas=corridas(obs))
    # S11: cada subida del contador es un disco marcado. Una bajada es destilde (o la selección
    # vaciada tras desmontar); no suma.
    previo: int | None = None
    for o in obs:
        if o.estado != "S11" or o.contador_s11 is None:
            continue
        if previo is not None and o.contador_s11 > previo:
            v.s11_marcados += o.contador_s11 - previo
        elif previo is None and o.contador_s11 > 0:
            v.s11_marcados += o.contador_s11
        previo = o.contador_s11
    # Tandas confirmadas: después de una corrida S25, aparece el "Obtenido" del desmontaje (S24)
    # o la selección vuelve a 0 — antes de que suba el contador (selección nueva) o de otra S25.
    # Ojo: al confirmar, el juego todavía muestra un frame de S11 CON la selección antes del
    # Obtenido (grabación 2026-10-03), así que ver S11 no corta.
    cs = v.corridas
    for i, c in enumerate(cs):
        if c.estado != "S25":
            continue
        previo = [o.contador_s11 for o in obs
                  if o.estado == "S11" and o.t < c.t_ini and o.contador_s11 is not None]
        declarado = previo[-1] if previo else None
        for o in obs:
            if o.t < c.t_fin:
                continue
            if o.estado == "S24" or (o.estado == "S11" and o.contador_s11 == 0):
                v.s11_tandas_confirmadas += 1
                break
            if o.estado == "S25" and o.t > c.t_fin:
                break
            if (o.estado == "S11" and o.contador_s11 is not None and declarado is not None
                    and o.contador_s11 > declarado):
                break
    # S10: niveles subidos dentro de cada visita al modal (el máximo menos el primero leído).
    for c in cs:
        if c.estado != "S10":
            continue
        niveles = [o.nivel_s10 for o in obs
                   if o.estado == "S10" and c.t_ini <= o.t <= c.t_fin and o.nivel_s10 is not None]
        if niveles:
            v.s10_niveles += max(niveles) - niveles[0]
    v.s22_discos = len({o.panel_s22 for o in obs if o.estado == "S22" and o.panel_s22})
    v.breves = {e: sum(1 for c in cs if c.estado == e) for e in ESTADOS_BREVES}
    return v


# --- lo que vio la app (líneas del log de la reproducción) --------------------------------------
_RE_ESTADO = re.compile(r"\[estado\] (\S+) → (\S+)")
_RE_TANDA = re.compile(r"tanda cerrada · (\d+) desmontados \((\d+) con datos, (\d+) sin\)")
_RE_MEJORA = re.compile(r"Upgrade S10: \[mejora\] nivel (\d+)→(\d+)")
_RE_S22 = re.compile(r"Disco S22 \(extracción\): ")


@dataclass
class VistoPorLaApp:
    estados: list[str] = field(default_factory=list)
    s11_declarados: int = 0
    s11_con_datos: int = 0
    s11_sin_datos: int = 0
    s11_tandas_cerradas: int = 0
    s10_niveles: int = 0
    s22_discos: int = 0
    breves: dict[str, int] = field(default_factory=dict)


def kpis_de_log(lineas: list[str]) -> VistoPorLaApp:
    k = VistoPorLaApp()
    for ln in lineas:
        if m := _RE_ESTADO.search(ln):
            k.estados.append(m.group(2))
        elif m := _RE_TANDA.search(ln):
            k.s11_tandas_cerradas += 1
            k.s11_declarados += int(m.group(1))
            k.s11_con_datos += int(m.group(2))
            k.s11_sin_datos += int(m.group(3))
        elif m := _RE_MEJORA.search(ln):
            k.s10_niveles += max(0, int(m.group(2)) - int(m.group(1)))
        elif _RE_S22.search(ln):
            k.s22_discos += 1
    k.breves = {e: k.estados.count(e) for e in ESTADOS_BREVES}
    return k


@dataclass
class Fila:
    kpi: str
    verdad: float
    app: float

    @property
    def cobertura(self) -> float | None:
        return None if not self.verdad else self.app / self.verdad


def comparar(v: Verdad, k: VistoPorLaApp) -> list[Fila]:
    filas = [
        Fila("S11 · discos marcados con datos", v.s11_marcados, k.s11_con_datos),
        Fila("S11 · tandas confirmadas y cerradas", v.s11_tandas_confirmadas, k.s11_tandas_cerradas),
        Fila("S10 · niveles subidos vistos", v.s10_niveles, k.s10_niveles),
        Fila("S22 · discos del Obtenido leídos", v.s22_discos, k.s22_discos),
    ]
    filas += [Fila(f"pantalla breve {e} vista", v.breves.get(e, 0), k.breves.get(e, 0))
              for e in ESTADOS_BREVES if v.breves.get(e)]
    return filas


def reporte_md(titulo: str, filas: list[Fila], extra: list[str] | None = None) -> str:
    out = [f"# {titulo}", "", "| KPI | verdad | la app | cobertura |", "|---|---|---|---|"]
    for f in filas:
        cob = "—" if f.cobertura is None else f"{f.cobertura:.0%}"
        out.append(f"| {f.kpi} | {f.verdad:g} | {f.app:g} | {cob} |")
    if extra:
        out += [""] + extra
    return "\n".join(out) + "\n"


# --- extracción por frame (la usa `tools/verdad_de_sesion.py`; corre OCR, sin apuro) -------------
def observar_frame(t: float, frame, detector, ocr) -> ObsFrame:
    """Lo que hay en un frame grabado, leído con el detector y los parsers de la app pero SIN
    cadencia ni votación: cada frame se mira entero. Lento a propósito (es la verdad de tierra)."""
    st = detector.classify(frame)
    o = ObsFrame(t=t, estado=st.code)
    try:
        if st.code == "S11":
            from app.core.parser_desmontaje import parse_header_counter
            o.contador_s11 = parse_header_counter(frame, ocr)
        elif st.code == "S10":
            from app.core.parser_disc_s10 import parse_disc_s10
            d = parse_disc_s10(frame, ocr)
            o.nivel_s10 = d.nivel if d is not None else None
        elif st.code == "S22":
            from app.core.parser_extraccion import parse_detail_disc
            d = parse_detail_disc(frame, ocr)
            if d is not None and (d.main_stat_canon or d.main_stat_raw) and d.subs:
                subs = ",".join(sorted(f"{s.nombre_canon or s.nombre_raw}:{s.valor}" for s in d.subs))
                o.panel_s22 = f"{d.set_name_raw}|{d.slot}|{d.main_stat_canon or d.main_stat_raw}|{subs}"
    except Exception:
        pass                                  # un frame ilegible no tumba la pasada entera
    return o
