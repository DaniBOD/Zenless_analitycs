# Página del PJ con la declaración de sets y stats — plan de implementación

> **Para quien ejecute:** inline, en esta sesión (Daniel: sin subagentes). Pasos con `- [ ]`.

**Objetivo:** reemplazar el modal del PJ por una página en el área de contenido, con la build
declarada a la derecha y cuatro ventanas flotantes que la editan sobre `EditorFichaPJ`.

**Arquitectura:** tres lecturas puras nuevas en `app/core/ficha_pj.py`, y un paquete de UI
`app/ui/pj_pagina/`:
- `datos.py`: lo que lee la página;
- `hoy.py`: lo que el modal mostraba;
- `pagina.py`;
- una ventana por archivo, con una base común.

`ShellWindow` gana una "página" fuera del sidebar. Las ventanas guardan en el momento y se vuelven a
dibujar leyendo la DB.

**Stack:** Python 3.11, PySide6, SQLite, pytest (offscreen).

**Spec:** [`2026-09-28_SPEC_Pagina_del_PJ_con_la_declaracion_de_sets_y_stats.md`](2026-09-28_SPEC_Pagina_del_PJ_con_la_declaracion_de_sets_y_stats.md)

## Restricciones globales

- **Escritura:** RNF-01 lo cumple `EditorFichaPJ._escribir` (backup por sesión, transacción, FK e
  integrity); la UI escribe SÓLO por el editor.
- **Sólo lectura** (`is_readonly()`): el editor no escribe, y la UI lo dice y deshabilita los controles.
- **Tests:**
  - los que escriben, sobre una COPIA de `db/danibod_zzz_v2.db` en `tmp_path`, con `DANIBOD_READONLY` borrado;
  - los de pantalla sin escritura, con `db_esquema_real` o la copia;
  - un sabotaje por regla (guarda `count == 1`); sha256 de la DB igual antes y después.
- **Commits:** uno por tarea, con el mensaje por archivo y
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Suite completa antes de cada push
  (`git push origin HEAD:main`). Push en los puntos de control: tras la Tarea 3 y al final.
- **Ediciones grandes** por scripts Python en el scratchpad (`PYTHONIOENCODING=utf-8`), con
  `assert count == 1`.
- **Sin rebuild del .exe.** QA en vivo con `tools\qa_launch.ps1 -ReadOnly -FromSource -NoAutoStart`.
- **Nombres de secundarios:** los canónicos de `stats_vocab` (`HP%`, `Prob. Crítica`…), como en
  Discos. Nombres de stats de fijos: `coherencia.ETIQUETA_STAT`. Números con coma decimal: `coherencia._n`.

## Mapa de archivos

| archivo | qué |
|---|---|
| `app/core/ficha_pj.py` (mod) | `Renglon2pc`, `renglones_2pc`, `FijoFicha`, `fijos_de_la_ficha`, `principales_validos` |
| `app/ui/shell/window.py` (mod) | `mostrar_pagina`, `volver`, `pagina_actual`; `_on_item` suelta la página |
| `app/ui/pj_pagina/__init__.py` | vacío |
| `app/ui/pj_pagina/datos.py` | `SetInfo`, `FichaPagina`, `pagina_pj`, `BLOQUE_DE_AVISO`, `avisos_por_bloque` |
| `app/ui/pj_pagina/hoy.py` | `_Hero`, `_Gauge`, `_SelectorPrioridad`, `Portada`, `HoyEnElJuego` (portados de `pj_modal/modal.py`) |
| `app/ui/pj_pagina/pagina.py` | `PjPagina` (portada + hoy + build declarada + "↺ todo a la guía") |
| `app/ui/pj_pagina/ventana.py` | `VentanaFlotante` (marco, franja sólo lectura, pie, `guardar`) |
| `app/ui/pj_pagina/ventana_secundarios.py`, `ventana_sets.py`, `ventana_principales.py`, `ventana_fijos.py` | una ventana cada uno |
| `app/ui/pj_modal/modal.py` | se BORRA (T3). `pj_modal/datos.py` queda: es la ficha "hoy en el juego" |
| `app/ui/pj_modal/datos.py` (mod) | se sacan `FichaPJ.avisos` y `avisos_del_pj` (T3): la autoridad pasa a `foto()` (B1) |
| `app/main.py` (mod) | `_abrir_ficha_pj` navega a la página; `_abrir_ficha_disco` cierra el modal antes de navegar |
| tests | `test_ficha_lecturas.py`, `test_shell_pagina.py`, `test_pj_pagina.py`, `test_pj_ventanas.py`; se adaptan `test_pj_modal.py` y `test_pj_modal_prioridad.py`; se borra `test_pj_modal_asesor.py` |

## Ajuste al SPEC (lo encontrado al planificar)

Al PJ también se llega desde **Armas** (`pj_pedido`) y desde el **modal del disco** (el dueño). El
"←" vuelve a **la vista de donde se vino**, con su nombre ("← Roster", "← Armas", "← Discos"). Desde
el modal del disco: se cierra el modal y se navega. Se anota en el SPEC en la Tarea 3.

---

### Tarea 1: las lecturas nuevas

**Archivos:** mod `app/core/ficha_pj.py`; test `app/tests/unit/test_ficha_lecturas.py`.

**Produce:**
```python
@dataclass(frozen=True)
class Renglon2pc:
    grupo: int
    sets: tuple[int, ...]            # el recomendado primero, después por id
    recomendado: int | None

def renglones_2pc(con, agente_id: int) -> dict[int, list[Renglon2pc]]   # 4pc → renglones en orden

@dataclass(frozen=True)
class FijoFicha:
    stat: str                        # vocabulario de agents ('prob_critico', …)
    objetivo: float | None           # el que usa el motor; None = desactivado por el usuario
    origen: str                      # 'kit' | 'set' | 'tuyo'
    de_la_guia: float | None         # el objetivo de kit/set (None si sólo es del usuario)
    actual: float | None             # stat leída del juego

def fijos_de_la_ficha(con, agent) -> list[FijoFicha]      # orden: stat
def principales_validos(slot: int, elemento: str | None) -> tuple[str, ...]
```

- [ ] **1. Tests que fallan.** Sobre una COPIA de la DB real (fixture `copia` = `shutil.copy` a
  `tmp_path`, `row_factory = Row`):
  ```python
  def test_renglones_de_ju_fufu_con_monarca(copia):
      ids = _ids(copia)                         # nombre → id, de agents y disc_sets
      r = renglones_2pc(copia, ids["Ju Fufu"])[ids["Monarca del Pináculo"]]
      assert [x.grupo for x in r] == [1, 2, 3, 4]
      assert r[0].recomendado == ids["Disco Sacudestrellas"]
      assert len(r[2].sets) == 2                # Voz Astral / Punk Hormonal

  def test_el_fijo_del_set_con_su_origen_y_lo_leido(copia):
      anby = AgentRepo(copia).get_by_id(_ids(copia)["Anby"])
      f = {x.stat: x for x in fijos_de_la_ficha(copia, anby)}["prob_critico"]
      assert (f.objetivo, f.origen, f.de_la_guia, f.actual) == (50, "set", 50, 48.2)

  def test_kit_y_set_vale_el_mayor_con_ese_origen(copia):
      dialyn = AgentRepo(copia).get_by_id(_ids(copia)["Dialyn"])
      f = {x.stat: x for x in fijos_de_la_ficha(copia, dialyn)}["prob_critico"]
      assert (f.objetivo, f.origen) == (100, "kit")

  def test_el_del_usuario_reemplaza_y_el_desactivado_queda_listado(copia):
      a = _ids(copia)["Anby"]
      copia.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'prob_critico', NULL)", (a,))
      copia.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'ataque', 2000)", (a,))
      agentes_cambiaron()
      f = {x.stat: x for x in fijos_de_la_ficha(copia, AgentRepo(copia).get_by_id(a))}
      assert (f["prob_critico"].objetivo, f["prob_critico"].origen, f["prob_critico"].de_la_guia) == (None, "set", 50)
      assert (f["ataque"].objetivo, f["ataque"].origen, f["ataque"].de_la_guia) == (2000, "tuyo", None)

  def test_una_sola_autoridad_con_el_motor(copia):       # B1, los 52 PJs
      for a in AgentRepo(copia).get_all():
          vivos = {f.stat: f.objetivo for f in fijos_de_la_ficha(copia, a) if f.objetivo is not None}
          assert vivos == a.stats_fijos, a.nombre

  def test_principales_validos_por_elemento():
      assert "Bono Daño Hielo" in principales_validos(5, "Hielo")
      assert not any(p.startswith("Bono Daño") and p != "Bono Daño Hielo" for p in principales_validos(5, "Hielo"))
      assert not any(p.startswith("Bono Daño") for p in principales_validos(5, "Lumen"))
      assert principales_validos(4, None) == tuple(sorted(CANONICAL_MAINS_VARIABLE[4]))
  ```
  Antes de escribirlos, verificar con una consulta de sólo lectura los nombres exactos (Ju Fufu,
  Monarca del Pináculo, Disco Sacudestrellas), que el grupo 3 tenga dos sets y la API de `AgentRepo`
  (`get_all`). Ajustar el test a la fuente, nunca al revés.
- [ ] **2. Correrlos:** fallan por import.
- [ ] **3. Implementar:**
  ```python
  def renglones_2pc(con, agente_id):
      out: dict[int, dict[int, list]] = {}
      if not _tabla_existe(con, "pj_sets_2pc"):
          return {}
      for s4, g, s, rec in con.execute(
              "SELECT set_4p_id, grupo, set_id, recomendado FROM pj_sets_2pc WHERE agente_id = ? "
              "ORDER BY set_4p_id, grupo, recomendado DESC, set_id", (agente_id,)):
          out.setdefault(s4, {}).setdefault(g, []).append((s, rec))
      return {s4: [Renglon2pc(g, tuple(s for s, _ in v), next((s for s, r in v if r), None))
                   for g, v in grupos.items()] for s4, grupos in out.items()}

  def fijos_de_la_ficha(con, agent):
      from app.db.repositories import cumple_condiciones_4pc
      kit = {s: o for s, o in con.execute(
          "SELECT stat, objetivo FROM pj_stats_fijos WHERE agente_id = ? AND requiere_set_4p_id IS NULL",
          (agent.id,))} if _tabla_existe(con, "pj_stats_fijos") else {}
      conds = leer_condiciones(con)
      del_set = ({c.stat: c.umbral for c in conds if c.set_id == agent.set_4p_id and c.tipo == "stat"}
                 if cumple_condiciones_4pc(conds, agent.set_4p_id, agent.rol, agent.elemento) else {})
      guia = {s: (max(kit.get(s, v), v), "set" if v > kit.get(s, v - 1) else "kit") for s, v in del_set.items()}
      for s, v in kit.items():
          guia.setdefault(s, (v, "kit"))
      usuario = {s: o for s, o in con.execute(
          "SELECT stat, objetivo FROM ajustes_usuario_fijos WHERE agente_id = ?", (agent.id,))} \
          if _tabla_existe(con, "ajustes_usuario_fijos") else {}
      out = []
      for s in sorted(set(guia) | set(usuario)):
          g_obj, g_org = guia.get(s, (None, "tuyo"))
          obj = usuario[s] if s in usuario else g_obj
          org = g_org if (s not in usuario or usuario[s] is None) and g_obj is not None else "tuyo"
          out.append(FijoFicha(s, obj, org, g_obj, agent.stats.get(s)))
      return out
  ```
  Ojo con el empate kit = set (Dialyn: 100 kit y 50 set → kit; un empate exacto → kit). Ojo con un
  objetivo del usuario sobre un stat de la guía: el origen pasa a `tuyo`, y `de_la_guia` conserva el
  de la guía para mostrar "(guía: 90)".
  `principales_validos`: `CANONICAL_MAINS_VARIABLE[slot]`, sin los "Bono Daño X" cuya X ≠ el
  elemento (Lumen: ninguno); ordenado.
- [ ] **4. Correr:** verde. **Sabotajes** (cada uno en rojo):
  - que el orden de los grupos se pierda (`ORDER BY set_4p_id, set_id`);
  - `"set" if v >= …` (el empate se va a set);
  - el origen de un ajuste del usuario queda en la guía;
  - que el slot 5 no filtre por elemento.
- [ ] **5. Commit** `feat(ficha): lecturas para la página — renglones del 2pc, origen de los fijos, principales por slot`.

### Tarea 2: una página fuera del sidebar en el shell

**Archivos:** mod `app/ui/shell/window.py`; test `app/tests/unit/test_shell_pagina.py`.

**Produce:** `ShellWindow.mostrar_pagina(w: QWidget) -> None`, `ShellWindow.volver() -> None`,
`ShellWindow.pagina_actual() -> QWidget | None`.

- [ ] **1. Tests que fallan** (`ShellWindow(install_native_frame=False)` con dos vistas "roster" y "armas"):
  - `mostrar_pagina(p)` → `current_view() is p`;
  - `volver()` → la vista activa del sidebar, y la página ya no está en el stack;
  - mostrar una segunda página reemplaza a la primera (una sola en el stack);
  - con la página abierta, `sidebar.select("armas")` → la vista armas, y la página se suelta;
  - `sidebar.select` sobre la clave ACTIVA también suelta la página (volver por el sidebar).
- [ ] **2. Implementar:**
  ```python
  def mostrar_pagina(self, pagina: QWidget) -> None:
      """Una página que no está en el sidebar (la del PJ): tapa la vista activa hasta `volver()`."""
      self._soltar_pagina()
      self._pagina = pagina
      self.stack.addWidget(pagina)
      self.stack.setCurrentWidget(pagina)

  def volver(self) -> None:
      self._soltar_pagina()
      w = self._views.get(self.sidebar.active_key())
      if w is not None:
          self.stack.setCurrentWidget(w)

  def _soltar_pagina(self) -> None:
      if self._pagina is not None:
          self.stack.removeWidget(self._pagina)
          self._pagina.deleteLater()
          self._pagina = None
  ```
  `self._pagina = None` en `__init__`; `_on_item` llama a `_soltar_pagina()` antes de cambiar.
- [ ] **3. Verde + sabotajes:** `_on_item` sin soltar; `volver` sin `removeWidget`.
- [ ] **4. Commit** `feat(shell): una página fuera del sidebar (mostrar_pagina / volver)`.

### Tarea 3: la página del PJ en reemplazo del modal

**Archivos:**
- nuevos: `app/ui/pj_pagina/{__init__,datos,hoy,pagina}.py`;
- se borra: `app/ui/pj_modal/modal.py`;
- mod: `app/ui/pj_modal/datos.py`, `app/main.py`, el SPEC;
- tests: nuevo `test_pj_pagina.py`; se adaptan `test_pj_modal.py` y `test_pj_modal_prioridad.py` a
  `PjPagina`/`hoy`; se borra `test_pj_modal_asesor.py`, y su prueba de falla se porta.

**Consume:** Tarea 1 y Tarea 2, `foto()`, `ficha_pj()`.
**Produce:**
```python
@dataclass(frozen=True)
class SetInfo:
    id: int; nombre: str; logo: str | None

@dataclass(frozen=True)
class FichaPagina:
    hoy: FichaPJ                     # la de pj_modal.datos
    foto: FotoFicha | None           # None = no se pudo leer la build declarada (se loguea)
    fijos: list[FijoFicha]
    renglones: dict[int, list[Renglon2pc]]
    sets: dict[int, SetInfo]         # los 30, para nombres y logos
    elemento: str | None

def pagina_pj(con, agente_id: int) -> FichaPagina | None          # None si el PJ no existe
BLOQUE_DE_AVISO = {"set_fuera_de_guia": "sets", "4pc_no_se_activa": "sets", "4pc_a_medias": "sets",
                   "principal_fuera_de_guia": "principales",
                   "substat_no_te_beneficia": "secundarios", "imprescindible_descartado": "secundarios",
                   "condicion_como_fijo": "fijos", "fijo_se_busca": "fijos"}
def avisos_por_bloque(avisos) -> dict[str, list[Aviso]]           # tipo desconocido → "otros"

class PjPagina(QWidget):
    volver_pedido = Signal()
    prioridad_cambiada = Signal(int, str)
    def __init__(self, leer: Callable[[], FichaPagina], *, editor=None, db_path=None,
                 volver_texto: str = "Roster", confirmar=None, parent=None)
    def refrescar(self) -> None
    boton_editar: dict[str, QPushButton]      # "sets" | "principales" | "secundarios" | "fijos"
    def textos_visibles(self) -> list[str]
```

- [ ] **1. Tests que fallan** (`test_pj_pagina.py`, sobre la copia):
  - `avisos_por_bloque`: cada tipo de `coherencia` cae en su bloque; uno inventado cae en "otros"
    (nada se pierde). Además, que `BLOQUE_DE_AVISO` cubra todos los tipos que emite `coherencia.py`
    (se leen del fuente con el regex `Aviso\([A-Z]+, "([a-z0-9_]+)"`).
  - La página de Anby muestra "← Roster", "HOY EN EL JUEGO" y "BUILD DECLARADA"; en SETS, "Monarca
    del Pináculo"; debajo de FIJOS, el texto de `fijo_se_busca`; el título lleva `ℹ 2`.
  - Los cuatro `boton_editar` existen.
  - Si `foto()` falla (monkeypatch que levanta), la página se arma igual, dice "No se pudo leer la
    build declarada" y se loguea (A2).
  - "↺ Volver todo a la guía" con `confirmar=lambda: False` no escribe; con `True` borra los ajustes
    (sha de la COPIA cambia; `leer_eleccion_pj` vacío).
  - Escape y "←" emiten `volver_pedido`.
  - Adaptar los tests del modal que importaban `PjModal`: las mismas afirmaciones (sin scoring ni
    botones de acción, "sin leer", filas del Armero, acento del elemento, prioridad) sobre
    `PjPagina`. La lista de botones permitidos suma "← Roster", los ✎ y "↺ Volver todo a la guía".
- [ ] **2. Implementar:**
  - `hoy.py`: mover `_Hero`, `_Gauge`, `_SelectorPrioridad`, `PRIO_NOTA`, `_ESCALA_BARRA`, `_lbl`,
    `_caps`, `_pixmap` y `_redondeado` de `pj_modal/modal.py` **sin cambios**. `Portada(ficha,
    acento, db_path)` con la portada ancha (sin la ×; el selector de prioridad arriba a la derecha).
    `HoyEnElJuego(ficha, acento)` = las columnas stats | build | arma del modal, **sin** el recuadro
    Asesor.
  - `pagina.py`: arriba "← {volver_texto}"; `Portada`; debajo un `QHBoxLayout`: `HoyEnElJuego`
    (stretch 3) | columna "BUILD DECLARADA" (stretch 2, con scroll vertical por si una guía es
    larga).
    - Cada bloque: caps con ✎ a la derecha, su contenido en texto y sus avisos (⚠ naranja `T.WARNING`,
      ℹ gris) debajo.
    - Lo del usuario, en `T.TEXT_PRIMARY` con "· tuyo"; lo de la guía, en `T.TEXT_SECONDARY`.
    - "otros" (si hay) arriba de todo.
    - `refrescar()` vuelve a llamar a `leer()` y reconstruye el contenido.
  - `pj_modal/datos.py`: sacar `FichaPJ.avisos` y `avisos_del_pj`, y restaurar su docstring (B1: los
    avisos salen de `foto()`).
  - `main.py`:
    ```python
    def _abrir_ficha_pj(self, agente_id: int):
        """Click en un PJ (Roster, Armas o el dueño de un disco) → la página de ese PJ."""
        if self._ui_con is None:
            return
        from app.ui.pj_pagina.datos import pagina_pj
        from app.ui.pj_pagina.pagina import PjPagina
        origen = {"roster": "Roster", "armas": "Armas", "discos": "Discos"}.get(self.sidebar.active_key(), "Volver")
        con = self._ui_con
        try:
            if pagina_pj(con, agente_id) is None:
                return
            pagina = PjPagina(lambda: pagina_pj(con, agente_id), volver_texto=origen)
        except Exception:
            log.exception("[roster] no se pudo armar la página del PJ %s", agente_id)
            return
        pagina.volver_pedido.connect(self.volver)
        roster = getattr(self, "_roster_view", None)
        if roster is not None:
            pagina.prioridad_cambiada.connect(roster.prioridad_actualizada)
        self.mostrar_pagina(pagina)
    ```
    En `_abrir_ficha_disco`: `modal.pj_pedido.connect(lambda pid: (modal.accept(), self._abrir_ficha_pj(pid)))`.
  - El SPEC: la frase del "←" según el origen (el ajuste de arriba).
- [ ] **3. Verde + sabotajes:**
  - `avisos_por_bloque` sin "otros" (un tipo nuevo se pierde);
  - `pagina_pj` sin try alrededor de `foto()`;
  - "↺" sin confirmar;
  - el aviso en un bloque equivocado.
- [ ] **4. Suite completa + push** (punto de control). QA en vivo: Daniel abre un PJ desde Roster,
  Armas y el dueño de un disco.
- [ ] **5. Commit** `feat(pj_pagina): la ficha del PJ pasa a ser una página, con la build declarada`.

### Tarea 4: la ventana flotante base y la de secundarios

**Archivos:** nuevos `app/ui/pj_pagina/ventana.py` y `ventana_secundarios.py`; mod `pagina.py` (✎
abre); test `test_pj_ventanas.py`.

**Produce:**
```python
class VentanaFlotante(QDialog):
    cambio = Signal()
    def __init__(self, titulo: str, leer, editor, acento: str, parent=None)
    def redibujar(self) -> None            # abstracto: reconstruye self.cuerpo desde self.leer()
    def guardar(self, accion: Callable[[], ResultadoFicha]) -> bool
    def a_la_guia(self) -> None            # abstracto: "↺ Esta parte a la guía"
    franja_solo_lectura: QLabel | None
    mensaje: QLabel                        # errores / motivo de no guardar
```
```python
def guardar(self, accion):
    try:
        res = accion()
    except (sqlite3.Error, ValueError) as e:
        log.exception("[ficha] no se guardó desde la ventana %s", self._titulo)
        self._decir(f"No se guardó: {e}. Backup: {getattr(self.editor, 'backup', None)}")
        return False
    if not res.escribio:
        self._decir(f"No se guardó: {res.motivo_no_escribio}")
        return False
    self._decir("")
    self.redibujar()
    self.cambio.emit()
    return True
```
`VentanaSecundarios.elegir_nivel(substat: str, nivel: int | None)` → `guardar(lambda:
editor.nivel_substat(id, substat, nivel))`. Cada ficha abre un `QMenu` con los 5 niveles de
`ficha_pj.NIVELES` y "↺ Como la guía" (`None`). El borde es sólido si
`substat in foto.eleccion.niveles` y tenue si no.

- [ ] **1. Tests que fallan** (copia, sin `DANIBOD_READONLY`):
  - `elegir_nivel("DEF%", 1)` en Ellen → `leer_eleccion_pj` tiene `{"DEF%": 1}`, la ficha DEF% queda
    en la fila Imprescindible con borde sólido, y aparece el ⚠ `substat_no_te_beneficia` en la ventana;
  - `elegir_nivel("DEF%", None)` lo vuelve a la guía;
  - el menú de una ficha tiene 6 acciones;
  - `a_la_guia()` borra todos los niveles del usuario de ese PJ;
  - con `DANIBOD_READONLY=1`: franja visible, cuerpo deshabilitado, y `elegir_nivel` no escribe (sha
    de la copia igual) y dice el motivo;
  - un editor que levanta `sqlite3.IntegrityError` → el mensaje "No se guardó" y ningún crash;
  - al cerrar la ventana, la página se refresca (la señal `cambio` → `pagina.refrescar`).
- [ ] **2. Implementar** lo de arriba. `a_la_guia` de secundarios: `nivel_substat(id, s, None)` por
  cada `s` de `foto.eleccion.niveles`, en un solo `guardar` (la lambda hace el bucle y devuelve el
  último resultado).
- [ ] **3. Verde + sabotajes:**
  - `guardar` sin `redibujar` (la ventana muestra lo viejo);
  - el except que devuelve True;
  - readonly sin deshabilitar;
  - borde sólido para todos.
- [ ] **4. Commit** `feat(pj_pagina): ventana flotante base y la de secundarios`.

### Tarea 5: la ventana de sets

**Archivos:** nuevo `ventana_sets.py`; mod `pagina.py`; tests en `test_pj_ventanas.py`.

**Produce:** `VentanaSets.elegir_4pc(set_id: int | None)`, `VentanaSets.elegir_2pc(set_id: int | None)`.
- `elegir_4pc(None)` → `editor.build(id, None)` (automático).
- `elegir_4pc(s)` → `editor.build(id, s, r[0].recomendado or r[0].sets[0] if r else None)`, con
  `r = renglones.get(s, [])`.
- `elegir_2pc(s)` → `editor.build(id, foto.set_4p_id, s)`. Deshabilitado si `foto.set_4p_id is None`,
  con el texto "Elegí primero el 4pc".

Listas:
- 4pc: "Automático", los `guia.sets_4pc` en orden (1, 2…) y "Otros sets" (el resto de los 30 por nombre).
- 2pc: los renglones del 4pc actual ("1 · Sacudestrellas (recomendado)", "3 · Voz Astral / Punk
  Hormonal") y "Otros sets", sin el set del 4pc.
- La nota de R24 debajo de los renglones.

- [ ] **1. Tests que fallan:**
  - en Ju Fufu con Monarca, los renglones se muestran en orden y con el recomendado marcado;
  - `elegir_4pc(Monarca)` en un PJ que no lo tenía deja 2pc = el recomendado del renglón 1;
  - `elegir_2pc` guarda con el 4pc vigente;
  - el set del 4pc no está en la lista del 2pc;
  - un set de "Otros" se marca "fuera de la guía" y, al elegirlo, aparece el ℹ `set_fuera_de_guia`;
  - "Automático" borra la fila de `ajustes_usuario_build`;
  - sin 4pc, el 2pc está deshabilitado.
- [ ] **2. Implementar. 3. Verde + sabotajes:**
  - el 2pc no se resetea al cambiar el 4pc;
  - los renglones sin orden;
  - el 4pc ofrecido como 2pc.
- [ ] **4. Commit** `feat(pj_pagina): la ventana de sets`.

### Tarea 6: la ventana de principales

**Archivos:** nuevo `ventana_principales.py`; mod `pagina.py`; tests.

**Produce:** `VentanaPrincipales.alternar(slot: int, stat: str)`.
- Parte de lo vigente, `set(foto.principales.get(slot, ()))`, y prende o apaga `stat`.
- Si queda vacío o igual a `foto.guia.principales.get(slot, set())`, llama a
  `editor.principales(id, slot, None)`; si no, `editor.principales(id, slot, sorted(nuevo))`.
- Los botones son `principales_validos(slot, elemento)`, marcados "guía" los de la guía.
- Cada slot tiene su "↺ como la guía".

- [ ] **1. Tests que fallan:**
  - en Ellen, `alternar(4, "Prob. Crítica")` agrega a la guía y guarda la lista;
  - apagarlo de nuevo vuelve a la guía (sin fila);
  - apagar el único vuelve a la guía, no queda vacío;
  - un principal fuera de la guía muestra el ⚠ `principal_fuera_de_guia`;
  - el slot 5 de Ellen no ofrece "Bono Daño Fuego".
- [ ] **2. Implementar. 3. Verde + sabotajes:**
  - no normalizar el "igual a la guía";
  - la lista vacía llega al editor (ValueError → mensaje).
- [ ] **4. Commit** `feat(pj_pagina): la ventana de principales`.

### Tarea 7: la ventana de fijos

**Archivos:** nuevo `ventana_fijos.py`; mod `pagina.py`; tests.

**Produce:** `VentanaFijos.cambiar(stat, objetivo: float)`, `.desactivar(stat)`, `.a_la_guia_fijo(stat)`,
`.agregar(stat, objetivo: float)`.

Un renglón por `FijoFicha`:
- etiqueta (`ETIQUETA_STAT`);
- origen ("del kit" / "del set" / "tuyo (guía: 90)");
- `QDoubleSpinBox` con el objetivo, que guarda en `editingFinished` si cambió;
- actual y cuánto falta (`_n`);
- estado ("el motor lo busca" si `actual < objetivo`, "cumplido" si `>=`, "sin leer" si `actual` es None);
- botones "desactivar" (sólo si `de_la_guia` no es None y está activo) y "↺".

"+ Agregar fijo": un combo con los stats del CHECK de `ajustes_usuario_fijos` que no tengan
objetivo, más un spin y "Agregar". El desactivado se muestra tachado con "reactivar" (= "↺").

- [ ] **1. Tests que fallan:**
  - en Anby, `cambiar("prob_critico", 55)` → origen "tuyo", `de_la_guia` 50, y "el motor lo busca";
  - `desactivar` → objetivo None y la línea tachada;
  - "↺" lo devuelve a 50 "del set";
  - `agregar("ataque", 2000)` aparece como "tuyo";
  - el combo no ofrece un stat que ya tiene objetivo;
  - un objetivo ≤ 0 no se guarda (el spin tiene mínimo > 0);
  - tras cualquier cambio, `fijos_de_la_ficha` coincide con `agent.stats_fijos` (B1, de nuevo).
- [ ] **2. Implementar. 3. Verde + sabotajes:**
  - `editingFinished` guarda aunque no cambió (un backup y una escritura por nada: el test cuenta escrituras);
  - "desactivar" ofrecido en uno "tuyo".
- [ ] **4. Commit** `feat(pj_pagina): la ventana de fijos`.

### Tarea 8: verificación visual y cierre

- [ ] **1. Render fuera de pantalla** (`QT_QPA_PLATFORM=offscreen`, `QT_QPA_FONTDIR=C:/Windows/Fonts`):
  - sobre la DB real en sólo lectura: la página de Anby, Ju Fufu, Gatillo y un PJ sin guía;
  - las cuatro ventanas abiertas sobre Ju Fufu;
  - sobre una copia: Ellen con DEF% en Imprescindible (el ⚠ de verdad).
  - Mirar una por una: que nada se corte y que los avisos queden debajo de su bloque. Enviarlas a Daniel.
- [ ] **2. Suite completa**, sha de la DB igual.
- [ ] **3. Docs:**
  - el SPEC con la tabla de commits y lo encontrado;
  - la línea del índice ("**Hecho**");
  - `BRIEF_ficha_sets_y_stats.md` con "Resuelto sin mockup (SPEC 2026-09-28)" arriba;
  - el SPEC de los avisos, con que el recuadro fue reemplazado;
  - la memoria del proyecto (`project_fase_a_criterio_equipar.md` y `MEMORY.md`).
- [ ] **4. Commit + push.** QA en vivo con Daniel en sólo lectura (ve que no guarda y lo dice). La
  escritura real la hace él con la app normal.
