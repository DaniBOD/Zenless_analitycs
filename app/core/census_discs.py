"""Censo de discos — módulo puro, sin Qt ni OpenCV.

El censo del roster se construyó sobre una ausencia: *"el menú de personajes no tiene contador
`N/M`"*, y de ahí salieron la asimetría PENDIENTE ≠ HUÉRFANO y el cierre explícito por F8. Sin
denominador, sólo una declaración humana puede afirmar que la pasada terminó.

**Para discos eso no aplica.** El header del inventario dice `Pistas de disco [339/3000]`, igual que
el `N/300` del desmontaje. Hay denominador escrito en pantalla, así que el censo puede saber cuánto
le falta sin preguntar — y, sobre todo, puede saber cuándo NO terminó.

## La brecha que el contador destapa

El sistema deduplica discos por identidad `(set, slot, main, {substat + rolls})`, y **22 pares del
inventario real son indistinguibles**: 345 identidades para 367 discos. Con 339 en pantalla, una
pasada perfecta registra ~317 y nunca llega a 339.

Declarar la pasada completa al alcanzar el total sería una condición que no se cumple jamás; bajar
el criterio para que cierre sería mentir sobre la cobertura. Se hace lo mismo que en el roster:
**reportar la brecha y decir que no se puede cerrar sola**. Si el resto son gemelos o discos sin
visitar es otra pregunta, y el censo no la contesta a las apuradas (RNF-02).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: Todavía no se pudo leer el contador del header: no hay denominador contra el cual medir.
SIN_ANCLA = "sin_ancla"
#: Hay denominador y faltan discos por registrar.
EN_CURSO = "en_curso"
#: Se registraron tantas identidades como discos dice el header (o más — ver `excedente`).
COMPLETA = "completa"


@dataclass(frozen=True)
class DiscSighting:
    """Un disco visto en el inventario.

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
    #: `True` si la identidad viene de la fila que la persistencia decidió tocar (autoridad
    #: única), `False` si se cayó a la identidad del parser. Importa porque la del parser se
    #: desdobla: el OCR lee el nombre del set inconsistente entre pasadas
    #: (`Firmamento Ilameante` / `Firmamento llameante`) y el conteo se infla en silencio.
    confirmada: bool = True


@dataclass
class DiscCensus:
    """Estado de una pasada de censo del inventario de discos."""

    total: int | None = None                 # denominador leído del header
    _abierta: bool = False
    _cerrada: bool = False
    _vistos: dict[tuple, DiscSighting] = field(default_factory=dict)
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
            log.debug("censo discos: total absurdo (%r) ignorado", n)
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

    def observe(self, s: DiscSighting, ts: float) -> bool:
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

        Nombra la causa PROBABLE sin afirmarla: con 22 pares indistinguibles en el inventario real,
        una brecha chica al final de una pasada completa son casi siempre gemelos — pero también
        podrían ser discos sin visitar, y el censo no tiene cómo separarlos.
        """
        f = self.faltan
        if not f:
            return None
        return (f"faltan {f} de {self.total}: o no se recorrieron, o son discos gemelos "
                f"(indistinguibles por identidad) que el censo cuenta una sola vez")

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
            "estado": self.estado,
            "total_pantalla": self.total,
            "registrados": self.registrados,
            "faltan": self.faltan,
            "excedente": self.excedente,
            "libres": self.libres,
            "con_dueno": self.con_dueno,
            "sin_resolver": self.sin_resolver,
            "provisorios": self.provisorios,
            "avisos": self.avisos,
            "motivo_incompleto": self.motivo_incompleto(),
        }
