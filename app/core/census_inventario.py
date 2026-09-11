"""Censo de un INVENTARIO con contador en pantalla — módulo puro, sin Qt ni OpenCV.

Sirve a los dos inventarios que tienen denominador escrito: discos (`Pistas de disco
[339/3000]`, pantalla S9) y W-Engines (`Amplificadores [57/2000]`, pantalla S30). Nació para
discos y se generalizó el 2026-09-06 **sin parametrizar conducta**: no había nada específico de
discos adentro —`identidad` es una tupla opaca a propósito, y `libre`/`dueno`/`confirmada`/
`faltan`/`excedente` aplican igual— así que duplicarlo habría dejado dos implementaciones de la
misma aritmética de cobertura, condenadas a derivar en silencio (B1). Lo único que cambia por
entidad es un texto.

El censo del roster se construyó sobre una ausencia: *"el menú de personajes no tiene contador
`N/M`"*, y de ahí salieron la asimetría PENDIENTE ≠ HUÉRFANO y el cierre explícito por F8. Sin
denominador, sólo una declaración humana puede afirmar que la pasada terminó.

**Para estos inventarios eso no aplica.** El header trae `N/M`, igual que el `N/300` del
desmontaje. Hay denominador escrito en pantalla, así que el censo puede saber cuánto le falta sin
preguntar — y, sobre todo, puede saber cuándo NO terminó.

## La brecha que el contador destapa

El sistema deduplica discos por identidad `(set, slot, main, {substat + rolls})`, y **22 pares del
inventario real son indistinguibles**: 345 identidades para 367 discos. Con 339 en pantalla, una
pasada perfecta registra ~317 y nunca llega a 339.

Declarar la pasada completa al alcanzar el total sería una condición que no se cumple jamás; bajar
el criterio para que cierre sería mentir sobre la cobertura. Se hace lo mismo que en el roster:
**reportar la brecha y decir que no se puede cerrar sola**. Si el resto son gemelos o discos sin
visitar es otra pregunta, y el censo no la contesta a las apuradas (RNF-02).

⚠️ **En armas la brecha es estructuralmente mayor, y por otro motivo.** Dos copias del mismo
W-Engine al mismo nivel y refinamiento son idénticas en TODO campo observable, y encima
`weapon_panel_signature_s30` es un hash del panel: mover la selección de una copia a su gemela ni
siquiera vuelve a disparar el parser. O sea que las copias son invisibles en la capa de
OBSERVACIÓN, no en la de deduplicación. Por eso `motivo_incompleto()` tiene un texto por entidad:
heredar el de discos ("gemelos") nombraría una causa que no es la de acá.

Y hay una causa de brecha que discos no tiene: un arma **fuera del catálogo** no se puede
persistir (`inventory_weapons.weapon_id` es `NOT NULL` y `weapons` es una tabla curada). Se cuenta
aparte, porque meterla en `faltan` haría el número ilegible: es una parte esperada y explicable de
la diferencia.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

#: Todavía no se pudo leer el contador del header: no hay denominador contra el cual medir.
SIN_ANCLA = "sin_ancla"
#: Hay denominador y faltan discos por registrar.
EN_CURSO = "en_curso"
#: Se registraron tantas identidades como discos dice el header (o más — ver `excedente`).
COMPLETA = "completa"


@dataclass(frozen=True)
class Sighting:
    """Un ítem visto en el inventario.

    `identidad` es opaca acá a propósito: el censo sólo la usa como clave, así que la definición
    de "mismo disco" vive en un solo lugar y este módulo no arrastra el parser. Quien la provee es
    el monitor, y desde el 2026-08-18 la saca de la FILA que la persistencia decidió tocar — no de
    un recálculo propio (ver `confirmada`).

    `libre` es una AFIRMACIÓN (se leyó la esquina del tile y no hay avatar), no la ausencia de
    `dueno`. Los dos falsos —`libre=False, dueno=None`— significan "no se pudo resolver", y el
    censo los cuenta aparte: mezclarlos con los libres inflaría una cuenta que después se usa
    para validar la pasada.
    """

    identidad: tuple
    libre: bool = False
    dueno: str | None = None
    #: `False` si el ítem no está en el catálogo curado y por eso NO se puede persistir. Cuenta
    #: para la cobertura —se lo vio— pero se reporta aparte: es una brecha con causa conocida, y
    #: mezclarla con "no se recorrió" haría ilegible el número.
    en_catalogo: bool = True
    #: `True` si la identidad viene de la fila que la persistencia decidió tocar (autoridad
    #: única), `False` si se cayó a la identidad del parser. Importa porque la del parser se
    #: desdobla: el OCR lee el nombre del set inconsistente entre pasadas
    #: (`Firmamento Ilameante` / `Firmamento llameante`) y el conteo se infla en silencio.
    confirmada: bool = True


@dataclass
class InventoryCensus:
    """Estado de una pasada de censo de un inventario con contador."""

    total: int | None = None                 # denominador leído del header
    #: Qué se está censando. NO cambia ninguna conducta: sólo el texto de `motivo_incompleto()`,
    #: porque la causa probable de la brecha es distinta en cada inventario.
    entidad: str = "discos"
    _abierta: bool = False
    _cerrada: bool = False
    _vistos: dict[tuple, Sighting] = field(default_factory=dict)
    _avisos: list[str] = field(default_factory=list)
    ts_apertura: float = 0.0
    ts_ultima: float = 0.0

    # --- ciclo de vida ------------------------------------------------------------------------

    def ensure_open(self, ts: float) -> bool:
        """Abre la corrida si no lo estaba. True si la abrió acá."""
        if self._abierta or self._cerrada:
            return False
        self._abierta = True
        self.ts_apertura = ts
        return True

    def cerrar(self, ts: float) -> None:
        self._cerrada = True
        self._abierta = False
        self.ts_ultima = ts

    @property
    def abierta(self) -> bool:
        return self._abierta and not self._cerrada

    # --- el ancla -----------------------------------------------------------------------------

    def anclar_total(self, n: int | None, ts: float) -> None:
        """Fija el denominador desde el contador del header.

        `None` es "no se pudo leer", nunca "cero": un frame de transición no puede borrar el ancla
        que ya se tenía, o el censo quedaría ciego a mitad de pasada.

        Un total que CAMBIA significa que el inventario se movió durante la pasada (farmeaste o
        desmontaste). Se re-ancla —quedarse con el viejo daría una cobertura falsa— pero queda
        avisado: cambiarlo en silencio borraría la única pista de que eso pasó.
        """
        if n is None:
            return
        if n <= 0:
            log.debug("censo %s: total absurdo (%r) ignorado", self.entidad, n)
            return
        if self.total is None:
            self.total = n
            return
        if n != self.total:
            self._avisar(f"el contador del header cambió: {self.total} → {n} "
                         f"(el inventario se movió durante la pasada)")
            self.total = n
        self.ts_ultima = ts

    # --- observación --------------------------------------------------------------------------

    def observe(self, s: Sighting, ts: float) -> bool:
        """Registra un disco. True si es la PRIMERA vez que se lo ve.

        No-op si la corrida no está abierta — una pasada de scroll emite en cada frame y no debe
        acumular fuera de una corrida.
        """
        if not self.abierta:
            return False
        self.ts_ultima = ts
        if s.identidad in self._vistos:
            # Re-visto: si ahora se resolvió el dueño (o se afirmó libre), la lectura mejor gana.
            previo = self._vistos[s.identidad]
            if previo.dueno is None and not previo.libre and (s.dueno or s.libre):
                self._vistos[s.identidad] = s
            return False
        self._vistos[s.identidad] = s
        return True

    # --- lo que se puede afirmar --------------------------------------------------------------

    @property
    def registrados(self) -> int:
        return len(self._vistos)

    @property
    def provisorios(self) -> int:
        """Registrados cuya identidad NO está confirmada contra una fila de la DB.

        Se cuentan igual —una pasada en seco tiene que poder medirse— pero se declaran aparte:
        presentar el total como si toda la cobertura tuviera el mismo respaldo le daría al número
        más autoridad de la que tiene."""
        return sum(1 for s in self._vistos.values() if not s.confirmada)

    @property
    def libres(self) -> int:
        return sum(1 for s in self._vistos.values() if s.libre)

    @property
    def con_dueno(self) -> int:
        return sum(1 for s in self._vistos.values() if s.dueno)

    @property
    def sin_resolver(self) -> int:
        """Vistos pero sin poder decir si están libres ni de quién son. Cuentan para la cobertura
        y NO para las otras dos cuentas."""
        return sum(1 for s in self._vistos.values() if not s.libre and not s.dueno)

    @property
    def fuera_de_catalogo(self) -> int:
        """Vistos que NO se pueden persistir porque el catálogo no los tiene. Cuentan para la
        cobertura y explican parte de la diferencia contra el total del header."""
        return sum(1 for s in self._vistos.values() if not s.en_catalogo)

    @property
    def faltan(self) -> int | None:
        """Cuántos discos faltan por registrar. `None` sin ancla — no se resta contra un total que
        no se leyó. Nunca negativo: el sobrante se reporta aparte (`excedente`)."""
        if self.total is None:
            return None
        return max(0, self.total - self.registrados)

    @property
    def excedente(self) -> int:
        """Identidades registradas POR ENCIMA del total del header. Distinto de cero es una señal
        de que algo no cierra (contador viejo, dos pasadas mezcladas), y callarlo dejaría una
        cobertura mayor al 100 % sin explicación."""
        if self.total is None:
            return 0
        return max(0, self.registrados - self.total)

    @property
    def progreso(self) -> tuple[int, int | None]:
        return (self.registrados, self.total)

    @property
    def estado(self) -> str:
        if self.total is None:
            return SIN_ANCLA
        return COMPLETA if self.registrados >= self.total else EN_CURSO

    def motivo_incompleto(self) -> str | None:
        """Por qué la pasada no cierra, en una línea, o `None` si cerró.

        Nombra la causa PROBABLE sin afirmarla, y el texto depende de la entidad porque la causa
        también: en discos son gemelos que la deduplicación colapsa; en armas, copias que la firma
        del panel ni siquiera vuelve a mirar. Decir "gemelos" en armas nombraría la causa
        equivocada.
        """
        f = self.faltan
        if not f:
            return None
        causa = _CAUSA_BRECHA.get(self.entidad, _CAUSA_BRECHA_GENERICA)
        return f"faltan {f} de {self.total}: {causa}"

    @property
    def avisos(self) -> list[str]:
        return list(self._avisos)

    def _avisar(self, msg: str) -> bool:
        """Agrega un aviso una sola vez. El header se lee en cada frame; avisar por lectura en vez
        de por cambio ahogaría el log."""
        if msg in self._avisos:
            return False
        self._avisos.append(msg)
        return True

    def resumen(self) -> dict:
        return {
            "entidad": self.entidad,
            "estado": self.estado,
            "total_pantalla": self.total,
            "registrados": self.registrados,
            "faltan": self.faltan,
            "excedente": self.excedente,
            "libres": self.libres,
            "con_dueno": self.con_dueno,
            "sin_resolver": self.sin_resolver,
            "provisorios": self.provisorios,
            "fuera_de_catalogo": self.fuera_de_catalogo,
            "avisos": self.avisos,
            "motivo_incompleto": self.motivo_incompleto(),
        }


#: Causa PROBABLE de la brecha, por entidad. Es lo único que la generalización parametriza.
_CAUSA_BRECHA_GENERICA = (
    "o no se recorrieron, o son ítems indistinguibles que el censo cuenta una sola vez"
)
_CAUSA_BRECHA = {
    "discos": ("o no se recorrieron, o son discos gemelos (indistinguibles por identidad) que "
               "el censo cuenta una sola vez"),
    # En armas el colapso NO es de la deduplicación sino de la OBSERVACIÓN: dos copias del mismo
    # W-Engine son idénticas en todo campo visible. Desde el 2026-09-10 las separa la POSICIÓN de
    # la selección en la grilla (`Monitor._ordinal_de_copia`); la brecha que queda es la de las
    # copias vistas sin posición localizable, donde no se puede saber si es otra copia y se cuenta
    # una sola (RNF-02). Hasta esa fecha este texto decía que la firma del panel no las distinguía:
    # dejó de ser cierto, y un reporte que explica la brecha con una causa que ya no existe manda a
    # buscar el problema al lugar equivocado.
    "armas": ("o no se recorrieron, o hay copias del mismo W-Engine que se vieron sin poder "
              "localizar la selección de la grilla — sin esa posición, dos copias idénticas "
              "cuentan como una"),
}

#: Nombres viejos: el flujo de discos no tiene por qué enterarse de la generalización.
DiscCensus = InventoryCensus
DiscSighting = Sighting


def write_weapon_census_report(resumen: dict | None,
                               fuera_de_catalogo: list[dict] | None = None
                               ) -> tuple[Path, Path] | None:
    """Escribe el cierre de una pasada de armas en `audit/censos/` (JSON + Markdown).

    El censo de discos no produce archivo —sólo loguea— y para armas sí hace falta, por una razón
    concreta: **la pasada descubre las armas que el catálogo no tiene, con su nombre español leído
    de pantalla**. Ese dato no está en ninguna wiki accesible (`audit/weapons_catalog_20260728.md`:
    *"las dos vías reales: capturarlas cuando aparezcan en pantalla… o una fuente en español que
    todavía no se encontró"*), así que el reporte es la entrada de la migración curada que después
    las da de alta. Perderlo significa volver a recorrer 57 tiles.

    Nada se da de alta solo: el archivo es material para revisar a mano. Auto-insertar con lo que
    devuelva el OCR repetiría el pecado original del catálogo, que fue emparejar por parecido.

    Mismo patrón que `census.write_census_report`: un archivo por corrida (el append atómico no
    está garantizado en Windows), `tmp` + `os.replace`, y **el reporte nunca puede tumbar el
    cierre** de la pasada.
    """
    if not resumen:
        return None
    registro = {"schema": "censo_armas/1", "resumen": resumen,
                "fuera_de_catalogo": list(fuera_de_catalogo or ())}
    try:
        from app.core.audit_paths import reservar_rutas, resolve_audit_dir
        rutas = reservar_rutas(resolve_audit_dir() / "censos", "censo_armas", ("json", "md"))
        textos = (json.dumps(registro, ensure_ascii=False, indent=2), _markdown_armas(registro))
        for destino, texto in zip(rutas, textos):
            tmp = destino.with_name(destino.name + ".tmp")
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, destino)
        return rutas[0], rutas[1]
    except Exception as e:  # noqa: BLE001 — el reporte nunca puede tumbar el cierre de la pasada
        log.warning("no se pudo escribir el reporte del censo de armas: %s", e)
        return None


def _markdown_armas(registro: dict) -> str:
    r = registro["resumen"]
    total = r["total_pantalla"]
    out = [
        "# Censo de W-Engines",
        "",
        (f"**Estado:** {r['estado']} — {r['registrados']}/"
         f"{total if total is not None else '?'} registradas"),
        "",
        "| | |",
        "|---|---|",
        f"| con dueño | {r['con_dueno']} |",
        f"| sin resolver | {r['sin_resolver']} |",
        f"| fuera de catálogo | {r['fuera_de_catalogo']} |",
        f"| provisorias (sin fila en la DB) | {r['provisorios']} |",
        f"| faltan | {r['faltan'] if r['faltan'] is not None else '?'} |",
        f"| excedente | {r['excedente']} |",
        "",
    ]
    if r.get("motivo_incompleto"):
        out += [f"> ⚠️ {r['motivo_incompleto']}", ""]
    for a in r.get("avisos") or ():
        out += [f"> ⚠️ {a}", ""]

    fuera = registro.get("fuera_de_catalogo") or []
    out += ["## Armas fuera del catálogo", ""]
    if not fuera:
        out += ["Ninguna: todo lo que se vio resolvió contra `weapons`.", ""]
    else:
        out += [
            (f"{len(fuera)} arma(s) que la pasada vio y **no se pudieron persistir**: "
             "`inventory_weapons.weapon_id` es `NOT NULL` contra un catálogo curado."),
            "",
            ("El nombre de abajo es el que se leyó **en pantalla, en español** — que es "
             "justamente el dato que ninguna wiki accesible publica y por el que estas filas no "
             "se pudieron cargar offline. Esta tabla es la entrada de la migración curada; "
             "**nada se da de alta automáticamente**."),
            "",
            "| nombre leído | rareza | nivel | ATK base | stat avanzado |",
            "|---|---|---|---|---|",
        ]
        for w in fuera:
            out.append(
                f"| `{w.get('nombre_raw') or '?'}` | {w.get('rareza') or '?'} | "
                f"{w.get('nivel') if w.get('nivel') is not None else '?'}"
                f"/{w.get('nivel_max') if w.get('nivel_max') is not None else '?'} | "
                f"{w.get('atk_base') or '?'} | {w.get('stat') or '?'} |"
            )
        out.append("")

    out += [
        "## Lo que esta corrida NO prueba",
        "",
        ("- **Las armas LIBRES, sólo como cantidad.** Desde el 2026-09-11 se escriben sin dueño: "
         "S30 las afirma después de medir el lugar del badge, y ninguna de las 11 capturas con "
         "dueño sale libre. Pero una libre no tiene más identidad que (arma, nivel, refinamiento) "
         "y su número de copia: si después se equipa, se sube de nivel o se recicla, su fila vieja "
         "queda (no se borra por ausencia), y volver a una copia ya vista tras un scroll puede "
         "sumar una fila de más. Un arma con dueño sin identificar sigue en `sin resolver`."),
        ("- **Las copias duplicadas, sólo por su lugar.** Dos copias del mismo W-Engine son "
         "idénticas en todo campo observable; el censo las separa por dónde está la selección en "
         "la grilla. Si el recuadro no se localiza, cuentan como una; y volver a una copia ya vista "
         "después de un scroll la cuenta otra vez (sale como excedente sobre el contador)."),
        "- **Nada sobre discos ni sobre el roster.**",
        "",
    ]
    return "\n".join(out)
