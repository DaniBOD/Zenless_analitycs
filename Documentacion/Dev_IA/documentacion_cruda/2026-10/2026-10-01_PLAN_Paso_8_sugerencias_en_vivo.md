# Paso 8: las sugerencias en vivo — plan de implementación

> **Para quien ejecute:** inline, en esta sesión (Daniel: sin subagentes). Pasos con `- [ ]`.

**Objetivo:** que cada drop y cada disco mirado en el inventario pase por el motor de Discos, con
toast sólo para un drop EQUIPAR o MEJORAR y la sugerencia en la card y en la región derecha.

**Arquitectura:** `app/core/sugerencias.py` saca el contexto del motor de `generar` a
`contexto_motor` y suma `sugerir_un_disco` (una sola autoridad). El controlador la llama en los dos
modos y pone en los payloads un bloque `sugerencia` ya resuelto (texto, tipo, detalle, mejora,
toast), así la vista no consulta la DB. El toast cambia el score sin calibrar por la mejora.

**Stack:** Python 3.11, PySide6, SQLite, pytest (offscreen).

**Spec:** [`2026-10-01_SPEC_Paso_8_sugerencias_en_vivo.md`](2026-10-01_SPEC_Paso_8_sugerencias_en_vivo.md)

## Restricciones globales

- **Una sola autoridad:** el vivo y Discos usan las mismas reglas (`recomendar` + la misma
  clasificación). El texto y el detalle, de `discos.datos.texto_sugerencia` y
  `disco_modal.datos.detalle_sugerencia`.
- **Calcular no escribe:** corre igual en sólo lectura. La sugerencia va en su propio try: ni la
  persistencia ni el censo dependen de ella.
- **Tests:**
  - lo que lee la DB real, sobre una COPIA;
  - un sabotaje por regla (guarda `count == 1`); sha256 de la DB igual antes y después.
- **Commits:** uno por tarea (mensaje por archivo, `Co-Authored-By: Claude Opus 5.5
  <noreply@anthropic.com>`). Suite completa antes del push. Ediciones grandes por scripts Python con
  `assert count == 1`.
- **Sin rebuild del .exe.** QA en vivo con `tools\qa_launch.ps1 -FromSource`.

## Mapa de archivos

| archivo | qué |
|---|---|
| `app/core/sugerencias.py` (mod) | `ContextoMotor`, `contexto_motor`, `_clasificar`, `sugerir_un_disco`; `generar` usa las tres |
| `app/ui/controller.py` (mod) | `_sugerencia_en_vivo(disc_parsed, result)` → bloque `sugerencia`; drops e inventario; log |
| `app/ui/toast.py` (mod) | `ToastData.mejora`; con mejora: "MEJORA +0,57", sin barra de urgencia ni `thr` |
| `app/main.py` (mod) | `_on_disc_show_toast` sólo si `payload["sugerencia"]["toast"]` |
| `app/ui/live/sugerencia.py` (nuevo) | `RecuadroSugerencia` (región derecha) |
| `app/ui/live/item_card.py`, `view.py` (mod) | la línea de la card; la región derecha; `drop_como_observacion` deja pasar `sugerencia` |
| tests | `test_sugerir_un_disco.py`, `test_controller_sugerencia_vivo.py`, `test_toast_mejora.py`, `test_live_sugerencia.py`; se ajustan los que leían `variant`/`score` del drop |

### El bloque `sugerencia` del payload (lo produce el controlador, lo leen vista, toast y main)

```python
{
    "texto": "EQUIPAR → Anby +0,57" | "Nada que hacer" | "sin sugerencia: falló el cálculo (ver log)",
    "tipo": "equipar" | ... | None,
    "conflicto": None,               # en vivo no se cruza con las demás sugerencias
    "detalle": [str, ...],           # detalle_sugerencia
    "destino": "Anby" | None,
    "mejora": 0.57 | None,           # delta
    "toast": bool,                   # sólo drop (S3/S6/S7) y tipo en {equipar, mejorar}
    "error": bool,
}
```

---

### Tarea 1: `contexto_motor` y `sugerir_un_disco`

**Produce:**
```python
@dataclass
class ContextoMotor:
    agentes: AgentRepo; arqs: ArchetypeRepo; sets_repo: DiscSetRepo; inv: InventoryDiscRepo
    nombres: dict[int, str]; prioridades: dict[int, str]; sets: dict[int, str]
    activos: list[Disc]; libres: list[Disc]; ctx: ScoringContext
    def builds(self, agente_id: int) -> dict[int, Disc]          # cacheado

def contexto_motor(con) -> ContextoMotor
def _clasificar(d: Disc, rec, c: ContextoMotor) -> tuple[str, Sugerencia | None]
    # ("sugerencia", s) | ("sin_cambio", None) | ("sin_nivel", None): el cuerpo del bucle de generar
def sugerir_un_disco(con, disco: Disc, contexto: ContextoMotor | None = None) -> SugerenciaDisco
```

- [ ] **1. Antes de tocar:** volcar `generar(DB)` (sólo lectura) a un JSON en el scratchpad (la
  línea de base del refactor).
- [ ] **2. Tests que fallan** (`test_sugerir_un_disco.py`, sobre una copia):
  - **paridad:** para todo disco activo, `sugerir_un_disco(con, d, c).propia` es igual a la propia
    de `generar` sin `conflicto` (los campos `tipo, disc_id, destino_id, slot, origen, reemplazo_id,
    delta`), salvo los discos que nombra un `armar_2pc`;
  - **un equipado bien puesto da `propia is None`;**
  - **un drop que no está en la DB** (id −1, libre, nivel 0) se evalúa: devuelve una sugerencia, y
    entra en los libres con los que se compara (como en `generar`, donde el propio disco está);
  - **un disco sin nivel leído** da `propia is None`, igual que lo que `generar` cuenta como `sin_nivel`.
- [ ] **3. Implementar:** mover el armado del contexto y el cuerpo del bucle de `generar` a
  `contexto_motor` / `_clasificar` **sin cambiar su lógica**. Para un disco que no esté en
  `c.libres` y no esté equipado: `libres = c.libres + [disco]`. La prioridad del destino, de
  `c.prioridades`.
- [ ] **4. Verde.** `generar(DB)` vuelto a volcar = la línea de base, byte a byte (refactor puro).
  **Sabotajes:**
  - el drop no entra en los libres;
  - `_clasificar` sin la rama `mover`;
  - la prioridad no se copia.
- [ ] **5. Commit** `refactor(sugerencias): contexto_motor y sugerir_un_disco, una sola autoridad con generar`.

### Tarea 2: el controlador calcula la sugerencia en vivo

**Consume:** `contexto_motor`, `sugerir_un_disco`, `texto_sugerencia`, `detalle_sugerencia`.
**Produce:** `MonitorController._sugerencia_en_vivo(disc_parsed, result, es_drop: bool) -> dict`
(el bloque de arriba); los payloads de `disc_detected` y `disc_observed` llevan `"sugerencia"`.

- [ ] **1. Leer** cómo arman el controlador `test_controller_payloads_vivo.py` y
  `test_controller_disc_observed.py`, y usar el mismo patrón.
- [ ] **2. Tests que fallan** (`test_controller_sugerencia_vivo.py`, DB copia):
  - un drop EQUIPAR → `toast` True, texto "EQUIPAR → X +n", `mejora` = delta;
  - un drop DESCARTAR → `toast` False y la card tiene su texto;
  - un disco de S9 que se sugiere mover → `toast` False aunque mejore;
  - en sólo lectura, lo mismo (y la DB copia no cambia);
  - si `sugerir_un_disco` levanta, el payload sale igual, con `error` True y `toast` False, y el log
    tiene el traceback;
  - el log tiene `[sugerencia] #… → …`.
- [ ] **3. Implementar:**
  - el `Disc` a evaluar: con `result.disc_id` (escritura), el de la DB; si no, el armado del
    parseado (id −1; equipado con el id del dueño en S17/S9);
  - `_build_payload` deja de llamar a `recomendar` con el contexto viejo: `variant`, `target`,
    `target_avatar` y `mind` salen de la sugerencia nueva; `score`, `urgency` y `threshold` se van;
  - `_build_observed_payload` suma la `sugerencia`.
- [ ] **4. Verde + sabotajes:**
  - toast para S9;
  - toast para descartar;
  - el except que corta el payload.

  Correr y ajustar los tests que leían `variant`/`score` del drop.
- [ ] **5. Commit** `feat(vivo): los drops y el inventario pasan por el motor de Discos`.

### Tarea 3: el toast con la mejora

- [ ] **1. Tests que fallan** (`test_toast_mejora.py`):
  - `main._on_disc_show_toast` con `toast` False no muestra nada; con True, muestra;
  - `ToastData(mejora=0.57)` pinta "MEJORA" y "+0,57" y no pinta "URGENCIA" ni "thr" (se verifica
    con el texto que dibuja el `paintEvent`, capturado con un `QPainter` espía o con
    `toast.textos_pintados()` si se agrega como introspección).
- [ ] **2. Implementar:** `ToastData.mejora: float | None = None`. En `paintEvent`, si `mejora` no es
  None: el bloque "MEJORA +0,57" en lugar de SCORE, y sin la barra de urgencia ni `thr`.
- [ ] **3. Verde + sabotajes:**
  - main sin la guarda de `toast`;
  - la barra de urgencia que sigue con mejora.
- [ ] **4. Commit** `feat(toast): la mejora real en vez del score sin calibrar; sólo si mejora a alguien`.

### Tarea 4: la card y la región derecha

- [ ] **1. Tests que fallan** (`test_live_sugerencia.py`):
  - un payload con `sugerencia` → la card muestra el texto con el color de `tokens.SUGERENCIA[tipo]`
    y la región derecha, el título "Sugerencia del motor" y las líneas del detalle;
  - "Nada que hacer" sin detalle; con `error`, el texto del error;
  - `drop_como_observacion` deja pasar `sugerencia` (y sigue sin dejar pasar `score`/`threshold`/`urgency`);
  - un payload sin `sugerencia` (los viejos) no rompe y deja la región vacía.
- [ ] **2. Implementar:** `RecuadroSugerencia(QFrame)` con `mostrar(sugerencia: dict | None)`;
  `LiveView` lo pone en `region_derecha` y lo actualiza en `on_disc_observed` / `on_disc_detected`;
  `ItemCard.mostrar_disco` pinta la línea.
- [ ] **3. Verde + sabotajes:**
  - la región que no se actualiza con el disco nuevo;
  - el color de otro tipo.
- [ ] **4. Commit** `feat(vivo): la sugerencia en la card y su detalle en la región derecha`.

### Tarea 5: verificación y cierre

- [ ] **1. Render** de la vista en vivo con tres payloads reales (un drop EQUIPAR armado sobre una
  copia, un S9 MOVER, un DESCARTAR) y del toast con la mejora; mirarlos y enviarlos.
- [ ] **2. Suite completa**, sha de la DB igual. Push.
- [ ] **3. QA en vivo con Daniel:**
  - pasada de censo S9 `-ReadOnly -Metrics`: 0 toasts; la latencia click→log contra 1203 ms
    [1172–1234] con `report_latency`;
  - drops farmeando: toast sólo los que mejoran.
- [ ] **4. Docs:**
  - el SPEC con commits y lo medido;
  - el índice;
  - `project_fase_a_criterio_equipar.md` y `MEMORY.md`;
  - la línea de base de latencia si cambió.
