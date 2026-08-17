"""Contabilidad de cobertura del censo de cuenta — la Fase 0.

Módulo **puro** a propósito, igual que `teardown_batch.py`: no importa OpenCV, ni OCR, ni sqlite,
ni Qt. Todo lo que decide se prueba con tuplas. Acá vive la parte del censo que no se puede
verificar mirando una captura.

## Por qué existe

La DB es transcripción manual nunca verificada contra el juego, y ya divergió. El censo invierte
la relación: la cuenta es la verdad, la DB su reflejo. Pero **RNF-03 prohíbe navegar el juego**,
así que el censo no es un proceso que el sistema ejecuta: es un recorrido que el usuario hace y el
sistema observa.

De ahí el corolario que ordena todo este módulo: *un censo que no sabe qué NO vio es peor que no
tener censo, porque produce una foto parcial con cara de completa.*

## Las dos asimetrías

**1. PENDIENTE ≠ HUÉRFANO, y la diferencia es una declaración humana.**
El menú de personajes **no tiene contador `N/M`** (verificado sobre las capturas), así que el
sistema no puede saber si el usuario recorrió hasta el final. No debe fingir que sí. `huerfano` es
una transición del CIERRE, nunca de la observación. Corolario asumido de frente: una corrida que
nunca se cierra no produce huérfanos jamás, y una **abandonada** tampoco — vencerse no es
terminar.

**2. Reportar un PJ nuevo pide más evidencia que reconocer uno conocido.**
Un falso positivo acá dispara el onboarding de un personaje que no existe. Por eso un texto que no
matchea contra el roster pero se **parece** a alguien conocido (`Astre Yoo` → Astra Yao) se trata
como lectura sucia de ese candidato, no como alta; y un PJ genuinamente desconocido necesita dos
lecturas concordantes antes de reportarse.

**3. El menú lista en GRIS a los personajes que NO se poseen**, mezclados con los propios
(verificado sobre `Menu_Personajes/Ejemplo_10.png`). El recorrido los lee sí o sí. `NO_POSEIDO`
existe para eso: ni cobertura ni alta.

⚠️ **La guarda del catálogo es PARCIAL y hay que saberlo.** `avatar_refs/` va por delante de la
posesión pero no cubre a todos: en Ejemplo_10 se cuentan ~9 grises en una sola pantalla contra
**5** de diferencia entre el catálogo y `agents`. Lo que queda afuera cae en `nuevos`, y por eso
ese reporte nombra las DOS lecturas posibles en vez de afirmar un alta.

**La señal definitiva es el CANDADO**: el tile de un no obtenido reemplaza el badge de rango por
un candado y muestra "Nivel 1" en gris. Es estructural —no una heurística de saturación, que ya
falló una vez separando paletas en vez de obtenido/no-obtenido—. Leerlo pide localizar el tile
seleccionado en la grilla inclinada de S15; cuando se haga, `MenuSighting` gana un campo y esta
clasificación deja de depender del catálogo.

## Monotonía

VISTO es absorbente dentro de una corrida: una lectura posterior mala no lo degrada. Es la misma
regla que gobierna al desmontaje (*"el scroll nunca borra lo ya capturado"*). La evidencia de
haber visto algo no se pierde porque un frame después salga borroso.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# --- umbrales -------------------------------------------------------------------------------
# Confianza del OCR (qué tan seguro está Paddle de los CARACTERES) por debajo de la cual el
# avistamiento no alcanza para dar por censado al PJ.
_CONF_MIN_VISTO = 0.80

# Similitud del match contra el roster (qué tan seguro está el sistema de la IDENTIDAD). Muy por
# encima de `_NAME_MIN_SIM=0.55` de `parser_agent_stats` a propósito: 0.55 alcanza para
# IDENTIFICAR a quién estás mirando, no para CENSAR que lo tenés.
_SCORE_MIN_VISTO = 0.75

# Similitud por encima de la cual un texto que NO matcheó se considera lectura sucia de un PJ
# conocido en vez de un PJ nuevo. No es afinado: es la salvaguarda que evita disparar el
# onboarding de un personaje inexistente por un OCR feo.
_NUEVO_MAX_SIM = 0.45

# Lecturas concordantes que exige un PJ fuera del roster antes de reportarse como alta.
_OBS_MIN_NUEVO = 2

_SCHEMA = "censo_roster/1"

# Estados de cobertura. `huerfano` no se escribe nunca durante la pasada (ver docstring).
PENDIENTE, VISTO, DUDOSO, HUERFANO = "pendiente", "visto", "dudoso", "huerfano"

# El menú lista en GRIS a los personajes que el jugador NO posee, mezclados con los suyos, así
# que el recorrido los lee sí o sí. `no_poseido` es su estado: ni cobertura (no son tuyos) ni
# alta (no son nuevos). Sin él, cada pasada dispararía el onboarding de todos los que te faltan.
NO_POSEIDO = "no_poseido"

_ILEGIBLES = {"sin_roi", "ocr_error", "ocr_vacio"}


def _norm(s: str | None) -> str:
    # Import local, mismo motivo que `teardown_batch._norm`: mantener este módulo libre de las
    # dependencias pesadas (numpy/cv2) que arrastra el parser.
    from app.core.parser_agent_stats import _norm_name
    return _norm_name(s or "")


@dataclass(frozen=True)
class MenuSighting:
    """Lo que el handler de S15 vio en UNA selección.

    El parser reporta números; la política de qué es VISTO, DUDOSO o PJ NUEVO la decide el censo.
    `candidato`/`score` son el mejor match y su similitud **cruda**, se haya superado o no el
    umbral de identificación: sin eso no se puede distinguir un PJ nuevo de un nombre conocido
    mal leído.
    """
    nombre: str | None        # canónico del roster; None = no superó el umbral de match
    texto_crudo: str | None   # lo que leyó el OCR, resuelva o no
    conf: float | None        # confianza del OCR
    candidato: str | None     # mejor match aunque no haya pasado el umbral
    score: float | None       # similitud de ese mejor match
    motivo: str               # 'ok' | 'sin_roi' | 'ocr_error' | 'ocr_vacio' | 'sin_match'


@dataclass
class CoverageRow:
    clave: str
    estado: str
    en_db: bool
    en_catalogo: bool = True
    agent_id: int | None = None
    texto_crudo: str | None = None
    n_obs: int = 0
    conf_max: float | None = None
    score_max: float | None = None
    ts_primera: float | None = None
    ts_ultima: float | None = None


@dataclass
class CensusDecision:
    """Qué debe loguear el monitor tras una observación. Espejo de `TeardownDecision`."""
    clave: str | None = None
    estado_previo: str | None = None
    estado: str | None = None
    es_nuevo: bool = False
    logs: list[str] = field(default_factory=list)


class RosterCensus:
    """Una pasada de censo del roster: se abre, acumula avistamientos, y se cierra por
    declaración del usuario."""

    def __init__(
        self,
        roster: Sequence[tuple[int, str]],
        *,
        catalogo: Iterable[str] | None = None,
        conf_min: float = _CONF_MIN_VISTO,
        score_min: float = _SCORE_MIN_VISTO,
        sink=None,
    ) -> None:
        """`roster` = lo que el jugador POSEE (tabla `agents`). `catalogo` = los personajes que
        EXISTEN en el juego; en el runtime sale de `avatar_refs/`, que se mantiene por delante de
        la posesión. La diferencia entre ambos es lo que el menú muestra en gris."""
        self._roster = list(roster)
        self._conf_min = conf_min
        self._score_min = score_min
        # norm → grafía canónica. `catalogo` son los que EXISTEN (incluidos los propios); los
        # GRISES se derivan restándole el roster. Que la resta la haga el censo y no el llamador
        # evita que un error de wiring mande un PJ propio a `no_poseido`.
        _roster_norm = {_norm(n) for _, n in self._roster}
        self._grises = {_norm(n): n for n in (catalogo or ()) if _norm(n) not in _roster_norm}
        # Persistencia opcional (duck-typed: `anotar_observacion`/`guardar_fila`/`marcar_cierre`).
        # El módulo sigue siendo puro: los tests de política no le pasan ninguno.
        self._sink = sink
        self.run_id: int | None = None
        self._reset()

    def _reset(self) -> None:
        self._abierta = False
        self._cerrada = False
        self._ts_apertura: float | None = None
        self._ts_ultimo: float | None = None
        self._filas: dict[str, CoverageRow] = {}
        self._avisos: list[str] = []
        self._motivo_drop: str | None = None

    # --- ciclo de vida --------------------------------------------------------------------
    def ensure_open(self, ts: float) -> bool:
        """Abre la pasada si no lo estaba. True si la abrió recién."""
        if self._abierta:
            return False
        self._reset()
        self._abierta = True
        self._ts_apertura = ts
        self._ts_ultimo = ts
        for agent_id, nombre in self._roster:
            self._filas[nombre] = CoverageRow(clave=nombre, estado=PENDIENTE, en_db=True,
                                              agent_id=agent_id)
        return True

    def restaurar(self, filas: Iterable[CoverageRow], *, run_id: int,
                  ts_apertura: float, ts_ultimo: float) -> None:
        """Reabre una pasada con la cobertura ya acumulada (multi-sesión).

        Siembra el roster ACTUAL primero y superpone lo persistido encima. Ese orden importa: un
        PJ onboardeado a mitad de pasada entra como PENDIENTE (pasó de verdad — Aria se cargó el
        mismo día que se censaba), y uno que desapareció del roster conserva lo ya observado en
        vez de evaporarse.
        """
        self.ensure_open(ts_apertura)
        self.run_id = run_id
        for f in filas:
            self._filas[f.clave] = f
        self._ts_ultimo = ts_ultimo

    def drop(self, motivo: str) -> None:
        """Abandona la pasada. **No** produce huérfanos: vencerse no es terminar."""
        self._abierta = False
        self._cerrada = False
        self._motivo_drop = motivo

    def cerrar(self, ts: float, motivo: str = "declarado_por_usuario",
               nota: str | None = None) -> dict | None:
        """Cierra la pasada por declaración del usuario. Es **la única** transición que fabrica
        huérfanos. Devuelve el registro, o None si la pasada no estaba abierta (ya cerrada,
        abandonada, o nunca abierta) — gate de idempotencia igual al de `TeardownBatch.commit`.
        """
        if not self._abierta or self._cerrada:
            return None
        for fila in self._filas.values():
            if fila.estado == PENDIENTE and fila.en_db:
                fila.estado = HUERFANO
                self._persistir_fila(fila)
        self._abierta = False
        self._cerrada = True
        if self._sink is not None and self.run_id is not None:
            self._sink.marcar_cierre(self.run_id, ts, motivo)
        return {
            "schema": _SCHEMA,
            "completo": motivo == "declarado_por_usuario",
            "motivo": motivo,
            "nota": nota,
            "ts_apertura": self._ts_apertura,
            "ts_cierre": ts,
            "resumen": self.resumen(),
            "vistos": [r.clave for r in self.vistos],
            "dudosos": [r.clave for r in self.dudosos],
            "nuevos": [{"clave": r.clave, "texto_crudo": r.texto_crudo, "n_obs": r.n_obs}
                       for r in self.nuevos],
            "no_poseidos": [r.clave for r in self.no_poseidos],
            "huerfanos": [r.clave for r in self.huerfanos],
            "avisos": list(self._avisos),
        }

    # --- observación ----------------------------------------------------------------------
    def observe(self, s: MenuSighting, ts: float) -> CensusDecision:
        """Procesa un avistamiento. No-op si la pasada no está abierta."""
        d = CensusDecision()
        if not self._abierta or self._cerrada:
            return d
        self._ts_ultimo = ts

        if s.motivo in _ILEGIBLES:
            if self._avisar(f"lectura ilegible ({s.motivo})"):
                d.logs.append(f"el nombre del PJ no se pudo leer ({s.motivo}) — nada que contar")
            return d

        clave, en_db, en_catalogo = self._resolver_clave(s)
        if clave is None:
            if self._avisar("texto sin clave utilizable"):
                d.logs.append("se leyó texto pero no dejó una clave utilizable — nada que contar")
            return d

        fila = self._filas.get(clave)
        if fila is None:
            fila = CoverageRow(clave=clave, estado=PENDIENTE, en_db=en_db,
                               en_catalogo=en_catalogo)
            self._filas[clave] = fila

        previo = fila.estado
        fila.n_obs += 1
        fila.ts_primera = fila.ts_primera if fila.ts_primera is not None else ts
        fila.ts_ultima = ts
        if s.texto_crudo:
            fila.texto_crudo = s.texto_crudo
        if s.conf is not None:
            fila.conf_max = s.conf if fila.conf_max is None else max(fila.conf_max, s.conf)
        if s.score is not None:
            fila.score_max = s.score if fila.score_max is None else max(fila.score_max, s.score)

        nuevo_estado = self._veredicto(s, fila)
        # VISTO es absorbente: una lectura posterior mala no lo degrada.
        if previo != VISTO:
            fila.estado = nuevo_estado

        d.clave = clave
        d.estado_previo = previo
        d.estado = fila.estado
        d.es_nuevo = not fila.en_db and fila.estado == VISTO
        if fila.estado != previo:
            d.logs.append(self._linea(fila))

        if self._sink is not None and self.run_id is not None:
            self._sink.anotar_observacion(self.run_id, ts, s, clave, fila.estado)
            self._persistir_fila(fila)
        return d

    def _persistir_fila(self, fila: CoverageRow) -> None:
        if self._sink is not None and self.run_id is not None:
            self._sink.guardar_fila(self.run_id, fila)

    def _resolver_clave(self, s: MenuSighting) -> tuple[str | None, bool, bool]:
        """A qué entidad se le atribuye el avistamiento: (clave, está_en_la_DB, está_en_el_catálogo).

        **El match exacto contra un gris va PRIMERO, y no es un detalle de orden.** Medido:
        `Lichter` —que no se posee— da 0.667 de similitud contra `Alice`, por encima del umbral
        de identificación (0.55). Si el match difuso corriera antes, un personaje que no tenés se
        disfrazaría de uno propio y le cargaría ruido. Un match exacto contra la lista de los que
        existen es evidencia mucho más fuerte que un parecido.
        """
        crudo = _norm(s.texto_crudo)
        if crudo and crudo in self._grises:
            return self._grises[crudo], False, True
        if s.nombre:
            return s.nombre, True, True
        # No matcheó, pero se parece bastante a alguien conocido ⇒ es una lectura sucia de ESE,
        # no un PJ nuevo. Se le atribuye al candidato (quedará DUDOSO, que pide repetición).
        if s.candidato and s.score is not None and s.score >= _NUEVO_MAX_SIM:
            return s.candidato, True, True
        if not crudo:
            return None, False, False
        return crudo, False, False

    def _veredicto(self, s: MenuSighting, fila: CoverageRow) -> str:
        conf_ok = s.conf is not None and s.conf >= self._conf_min
        if fila.en_db:
            # Sin `nombre` no hubo match: por bueno que sea el OCR, la identidad no está
            # confirmada (es el caso del casi-acierto atribuido al candidato).
            score_ok = s.score is not None and s.score >= self._score_min
            return VISTO if (s.nombre and conf_ok and score_ok) else DUDOSO
        # Fuera de la DB pero dentro del catálogo: es un gris. Estado terminal — verlo mil veces
        # no lo vuelve ni tuyo ni nuevo.
        if fila.en_catalogo:
            return NO_POSEIDO
        return VISTO if (fila.n_obs >= _OBS_MIN_NUEVO and conf_ok) else DUDOSO

    def _linea(self, fila: CoverageRow) -> str:
        vistos, total = self.progreso
        conf = f" conf {fila.conf_max:.2f}" if fila.conf_max is not None else ""
        if fila.estado == NO_POSEIDO:
            return f"{fila.clave} — no lo poseés (gris del menú), no se cuenta"
        if not fila.en_db:
            que = "NO RECONOCIDO" if fila.estado == VISTO else "texto desconocido"
            return f"{fila.texto_crudo or fila.clave} — {que}{conf}"
        marca = "visto" if fila.estado == VISTO else "dudoso (repetir)"
        return f"{fila.clave} — {marca}{conf} · {vistos}/{total}"

    def _avisar(self, msg: str) -> bool:
        """Agrega un aviso una sola vez. True si es nuevo, para loguear por flanco."""
        if msg in self._avisos:
            return False
        self._avisos.append(msg)
        return True

    # --- lectura --------------------------------------------------------------------------
    @property
    def abierta(self) -> bool:
        return self._abierta

    @property
    def cerrada(self) -> bool:
        return self._cerrada

    @property
    def avisos(self) -> list[str]:
        return list(self._avisos)

    def filas(self, estado: str | None = None, *, en_db: bool | None = None) -> list[CoverageRow]:
        out = list(self._filas.values())
        if estado is not None:
            out = [r for r in out if r.estado == estado]
        if en_db is not None:
            out = [r for r in out if r.en_db is en_db]
        return out

    @property
    def vistos(self) -> list[CoverageRow]:
        """Del roster de la DB. Los que están en el juego y no en la DB van en `nuevos`."""
        return self.filas(VISTO, en_db=True)

    @property
    def pendientes(self) -> list[CoverageRow]:
        return self.filas(PENDIENTE, en_db=True)

    @property
    def dudosos(self) -> list[CoverageRow]:
        return self.filas(DUDOSO)

    @property
    def nuevos(self) -> list[CoverageRow]:
        """Nombres leídos que NO están ni en la DB ni en el catálogo de arte, con evidencia
        suficiente. Admiten **dos lecturas** y el sistema no puede separarlas desde el nombre:
        un personaje recién salido, o uno que no poseés y todavía no tiene arte. El reporte dice
        las dos (RNF-02) — nunca 'alta confirmada'."""
        return self.filas(VISTO, en_db=False)

    @property
    def no_poseidos(self) -> list[CoverageRow]:
        """Los grises del menú: existen en el juego, no son tuyos, y su ausencia de la DB es
        correcta. Ni cobertura ni alta."""
        return self.filas(NO_POSEIDO)

    @property
    def huerfanos(self) -> list[CoverageRow]:
        """Vacío hasta cerrar, a propósito: sin declaración de cierre no hay huérfanos."""
        return self.filas(HUERFANO)

    @property
    def progreso(self) -> tuple[int, int]:
        return len(self.vistos), len(self._roster)

    def resumen(self) -> dict:
        vistos, total = self.progreso
        return {
            "total_db": total,
            "vistos": vistos,
            "dudosos": len(self.dudosos),
            "pendientes": len(self.pendientes),
            "nuevos": len(self.nuevos),
            "no_poseidos": len(self.no_poseidos),
            "huerfanos": len(self.huerfanos),
            "cobertura": (vistos / total) if total else 0.0,
        }


# --- reporte ---------------------------------------------------------------------------------

def _markdown(reg: dict) -> str:
    r = reg["resumen"]
    pct = f"{r['cobertura'] * 100:.0f}%"
    L: list[str] = [
        "# Censo de roster",
        "",
        f"- **completo:** {'sí' if reg['completo'] else 'no'} · cerrada por: `{reg['motivo']}`",
        f"- **cobertura:** {r['vistos']}/{r['total_db']} ({pct})",
        "",
    ]

    def bloque(titulo: str, items: list[str], nota: str | None = None) -> None:
        L.append(f"## {titulo} ({len(items)})")
        if nota:
            L.append(f"> {nota}")
        L.extend(f"- {i}" for i in items) if items else L.append("_ninguno_")
        L.append("")

    bloque("✅ Vistos", reg["vistos"])
    bloque("⚠️ Dudosos", reg["dudosos"],
           "Se vieron pero con lectura floja. **Volvé a seleccionarlos** — no son huérfanos.")
    bloque("⬜ No poseídos", reg["no_poseidos"],
           "Existen en el juego y no son tuyos: el menú los lista en gris. Su ausencia de la DB "
           "es correcta.")
    bloque("🆕 No reconocidos", [f"`{n['texto_crudo'] or n['clave']}` ({n['n_obs']} lecturas)"
                                 for n in reg["nuevos"]],
           "Nombres que no están ni en tu roster ni en el catálogo de arte. Admiten **dos "
           "lecturas** y el sistema no puede separarlas desde el nombre: un PJ nuevo, o uno que "
           "**no poseés** y todavía no tiene arte. Si es lo primero → `Onboarding_Nuevo_PJ.md`.")
    bloque("❓ Huérfanos", reg["huerfanos"],
           "Están en la DB y el recorrido NO pasó por ellos. **No se borran** (RNF-02): se marcan "
           "con la fecha y los arbitrás vos.")

    L += [
        "## Lo que esta corrida NO prueba",
        "",
        ("- Que los huérfanos no existan en la cuenta. Prueba que **el recorrido no pasó por "
         "ellos** — que no es lo mismo."),
        "- Nada sobre discos ni sobre armas.",
        "",
    ]
    if reg.get("avisos"):
        L += ["## Avisos", ""] + [f"- {a}" for a in reg["avisos"]] + [""]
    return "\n".join(L)


def write_census_report(registro: dict | None) -> tuple[Path, Path] | None:
    """Escribe el registro de una pasada en `audit/censos/` (JSON + Markdown). None si no hay
    nada que escribir — una corrida **abandonada** no produce reporte, porque no declara nada.

    Un archivo por corrida (no JSONL): el append atómico no está garantizado en Windows. `tmp` +
    `os.replace`, mismo patrón que `write_teardown_record` y `FarmSession._persist`.
    """
    if not registro:
        return None
    try:
        from app.core.audit_paths import resolve_audit_dir
        carpeta = resolve_audit_dir() / "censos"
        carpeta.mkdir(parents=True, exist_ok=True)
        # Hora local a propósito: el sello es para que un humano ubique la corrida en su día.
        sello = f"{datetime.now():%Y%m%d_%H%M%S_%f}_censo_roster"  # noqa: DTZ005
        salidas = []
        for ext, texto in (("json", json.dumps(registro, ensure_ascii=False, indent=2)),
                           ("md", _markdown(registro))):
            destino = carpeta / f"{sello}.{ext}"
            tmp = destino.with_suffix(".tmp")
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, destino)
            salidas.append(destino)
        return salidas[0], salidas[1]
    except Exception as e:  # noqa: BLE001 — el reporte nunca puede tumbar el cierre de la pasada
        log.warning("no se pudo escribir el reporte del censo: %s", e)
        return None
