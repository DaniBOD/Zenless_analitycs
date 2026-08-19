# La red de emergencia que el `.exe` nunca tuvo

> **2026-08-19.** Salió de revisar un empaquetado ajeno: el worktree que arregló `farm_nodes.toml`
> preguntó si convenía meter 34 MB de baselines al bundle. La pregunta tenía dos opciones y las dos
> eran falsas.

---

## 1. La pregunta mal planteada

> *¿Los meto al spec (+34 MB) o el `.exe` asume que el repo está al lado?*

El `.exe` **no llega al repo por ninguna vía**. En `agent_identifier.py`:

```python
_AUDIT_DIR = Path(__file__).resolve().parents[2] / "audit"
```

| entorno | `__file__` | `parents[2]` | resultado |
|---|---|---|---|
| desarrollo | `<repo>/app/core/agent_identifier.py` | `<repo>` | `<repo>/audit/` ✅ |
| congelado | `_internal/app/core/agent_identifier.py` | `_internal` | `_internal/audit/` ❌ |

Esa carpeta no existe en el bundle. O sea que el auto-restore de la librería de avatares
**ya estaba muerto del lado empaquetado**, en silencio, desde que existe.

No era un riesgo futuro condicionado a que se vacíe `%LOCALAPPDATA%`. La red no estaba puesta.

## 2. Por qué importa: el modo de falla no es el ruidoso

"Volvés a 0 dueños" habría sido el caso fácil. Lo que pasó el 2026-07-31 fue lo otro: el grid quedó
con la semilla `-ico` y **nombró mal con confianza** — 4,3 % top-1, 14 discos ajenos atribuidos a
Cissia. Eso no se ve mirando el log; se ve meses después, en los datos.

Una red de emergencia que nunca se ejerce en desarrollo tampoco se testea en desarrollo. El test que
existía (`test_los_baselines_versionados_existen`) verificaba que los archivos estuvieran ahí —
cierto en dev, irrelevante en el `.exe`.

## 3. El arreglo, y por qué salió gratis

Los tres `.npz` van a **`app/resources/badge_baselines/`**. Esa ruta resuelve con el mismo mecanismo
que `detector.TEMPLATES_DIR` y `farm_nodes._DEFAULT_TOML`, y no hizo falta tocar el spec porque el
mismo día anterior había pasado a copiar `app/resources` **entera**.

**Verificado en los dos extremos, no razonado:**

```
# el .exe dejó escrito a dónde resuelve esa regla:
FileNotFoundError: '...\_internal\app\resources\farm_nodes.toml'

# y el bundle nuevo tiene:
_internal/app/resources/badge_baselines/avatar_badge_v2_...npz   24151128
_internal/app/resources/badge_baselines/avatar_detbadge_v2_...   6105775
_internal/app/resources/badge_baselines/avatar_row_v2_...        4181828
```

`_internal/audit/` sigue sin existir — era la ruta muerta.

## 4. Los dos hallazgos de costado

**`preseed_badge_lib.py` tenía su propia lista de baselines, y discrepaba.**
`--source snapshot --surface grid` reinstalaba `avatar_badge_v2_snapshot_20260612_full47.npz` — el de
**junio**, sin Aria y sin el dedup — mientras `BadgeSurface.load` repone el de agosto. Dos
autoridades para "cuál es el baseline", en desacuerdo activo y sin que nadie lo notara. Ahora la
tool defiere a `_BASELINES`.

**`tools/audit_s9_surfaces.py` mutaba la librería con solo mirarla.** Construía `AgentIdentifier()`
a secas, que poda y persiste al construirse. Lo cazó `test_las_herramientas_de_tools_deciden_prune_
explicitamente`, un test que el proyecto ya tenía puesto justo para eso, escrito después de que
`audit_badge_lib` borrara 4 refs de "N.º 11" por el mismo motivo.

## 5. El precio de "la carpeta entera"

Bundlear `app/resources` completa es la decisión correcta —enumerar falló dos veces— pero tiene un
costo: cualquier archivo que caiga ahí viaja en el `.exe`. Un snapshot suelto son 24 MB que nadie
pidió, sobre un bundle de 1,3 GB donde nadie los va a notar.

Se paga con un test (`test_la_carpeta_de_baselines_no_junta_archivos_de_mas`) que exige que la
carpeta contenga **exactamente** los tres que `_BASELINES` declara, en vez de con una lista que hay
que acordarse de actualizar. Saboteado con un archivo intruso para confirmar que falla.

Reparto: `audit/` = historia con fecha, no se empaqueta. `app/resources/badge_baselines/` = los tres
que la app repone. Promover un snapshot a baseline es una decisión explícita, no un efecto de
costado de `--save-snapshot`.

---

## Estado

Suite completa **2390 passed · 33 skipped · 1 xfailed**. Ruff `app/` en **592** (baseline exacto).
DB de dominio intacta (PRAGMAs verdes, sin reportes espurios). Commit `9189158` en main.

**Falta rebuildear el `.exe` del repo** — el de `app/build/dist` es anterior a todo esto.
