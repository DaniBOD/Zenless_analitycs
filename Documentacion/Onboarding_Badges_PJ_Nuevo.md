# Onboarding de badges — incorporar un PJ nuevo al reconocimiento visual

> **Cuándo se usa:** sacaste un PJ nuevo y querés que el sistema lo reconozca en pantalla: que
> sepa que estás parado en su equipamiento y que sus discos y su W-Engine son de él.
>
> **Última corrida: Aria, 2026-08-16** — salió redonda siguiendo esto al pie: 6/6 discos con
> dueño correcto, la métrica sin moverse, y el lazo del §3 cerrándose en el slot 2 tal cual está
> descrito. Dejó dos datos útiles, los dos en §3.
>
> Esto es **aparte** del [onboarding de datos](./Onboarding_Nuevo_PJ.md) (filas en `agents`,
> thresholds, sinergias). Aquel carga lo que el PJ *es*; este enseña a *reconocerlo*.
>
> **Tiempo:** ~10 minutos, casi todo navegando el juego.

---

## 0. Qué hay que llenar

El sistema reconoce a un PJ por su avatar en tres lugares distintos de la pantalla. Cada uno tiene
su propia librería, porque **comparar like-with-like es lo que da robustez**: el mismo PJ recortado
con dos encuadres distintos no matchea (medido, Fase 5R).

| superficie | dónde aparece | para qué sirve | cómo se llena |
|---|---|---|---|
| **`row`** | barra superior de Equipamiento (S8) y de Atributos (S18/S19) | saber **en qué PJ estás parado** | screenshot (§2) |
| **`grid`** | columna izquierda del detalle de disco (S17) | saber **de quién es el disco** | cosecha en vivo (§3) |
| **`detail`** | junto a "Nivel 15/15", en el detalle de disco y de arma | dueño del disco y del **W-Engine** | cosecha en vivo (§3) |

Un PJ sin refs **no rompe nada**: la superficie se abstiene, que es el comportamiento correcto
(RNF-02). Lo que se pierde es cobertura, no corrección.

---

## 1. Antes de empezar

El PJ tiene que existir en la tabla `agents` con su nombre canónico — las librerías **canonizan el
label contra el roster antes de guardar**, y un PJ que no está en la DB simplemente no se aprende.
Si todavía no lo cargaste, hacé primero [`Onboarding_Nuevo_PJ.md`](./Onboarding_Nuevo_PJ.md) §3.

Equipale sus 6 discos y su W-Engine. La cosecha solo aprende del **disco equipado**, porque ahí el
juego mismo confirma de quién es (el botón dice "Desequipar").

---

## 2. `row` — un screenshot alcanza

**El `row` NO se cosecha en vivo en modo QA**: su gate de persistencia es `not is_readonly()`, así
que con `-ReadOnly` nunca guarda. Se llena desde una captura.

1. Andá a **Equipamiento** del PJ (la pantalla del hexágono de discos).
2. Sacá un screenshot y guardalo en
   `Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/`.
3. Cargalo:

```bash
.venv\Scripts\python.exe tools\preseed_badge_lib.py --surface row --source frame --frame "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_11.png" --label "Aria"
```

Salida esperada:

```
  Ejemplo_11.png: ref agregada a 'Aria'
'Aria': 0 -> 1 refs
  DESPUÉS  : 51 clases · 366 refs · min 1 max 8
```

> **Si decís el nombre equivocado, envenenás la librería.** Una ref mal etiquetada es el patrón
> Ben=Soukaku que costó días de limpieza. Y no se puede automatizar: contra el arte `-ico` las
> distancias quedan todas en ~0.44-0.49, y por firma de color del splash el resultado ni siquiera
> es una biyección. **Confirmá a ojo cuál es cuál antes de correr el comando.**

Con **una** ref alcanza para que lo identifique. Si querés más robustez, repetí con capturas de
S18 (Atributos base) — el `row` usa las dos pantallas.

---

## 3. `grid` y `detail` — cosecha en vivo

Estas dos sí se cosechan solas mientras navegás, en modo readonly.

```powershell
tools\qa_launch.ps1 -FromSource -ReadOnly -BadgeHarvest -NoRamGuard -IdDiag
```

Después, **por cada PJ nuevo**:

1. **Entrá desde el menú de personajes.** No es opcional: S15 lee su nombre por OCR y siembra el
   latch. Ese nombre leído en pantalla es la evidencia más certera que hay, y es lo que etiqueta
   la cosecha.
2. **Equipamiento → abrí un disco equipado.**
3. **Pasá por los 6 slots**, quedándote unos segundos en cada uno. Cada disco es un tiro
   independiente; el recorte del detalle sale ~1 de cada 4 frames.

Lo que vas a ver en el log (`%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\app.log`):

```
AgentIdentifier: badge aprendido para 'Aria'
[id_diag] ... slot=1 assigned=Aria voted=-    grid_votes=[-]          ← todavía sin refs
[id_diag] ... slot=2 assigned=Aria voted=Aria grid_votes=[Aria:0.94]  ← ya la nombra
```

**El lazo se cierra solo**: el primer disco aprende, del segundo en adelante ya la reconoce. Eso
funciona porque el grid **arranca abstenido** en un PJ sin refs — no hay veto que estorbe.

**No esperes 6 refs por superficie.** Medido con Aria (2026-08-16), los 6 slots dejaron **7 refs
de `grid` pero solo 3 de `detail`**, y esa asimetría es el dedup funcionando, no una pasada
incompleta: el tile del grid cambia con el disco, el avatar del panel de detalle **no**. Si ves
`detail` sumando una ref por disco, el dedup dejó de andar — eso es lo que infló las librerías
hasta agosto.

**Y ojo con el orden**: si el PJ todavía no está en `agents`, esta pasada **no guarda nada y el
log no te lo dice** — `learn` canoniza contra el roster y descarta en silencio. Es el §1, y es
literal.

---

## 4. Verificar (obligatorio)

Cosechar mal es peor que no cosechar: una ref con la etiqueta equivocada contamina el vecindario
del descriptor y se lleva discos ajenos. **Una sola ref basta para hacer de imán.**

```bash
.venv\Scripts\python.exe tools\measure_badge_lib.py --against-labeled --surface grid
```

El número que importa **no es el absoluto, es que no haya cambiado**:

```
TOP-1: 153/164 = 93.3%  |  ABSTENCIÓN: 4.3%  |  WRONG: 4/164 = 2.4%
IMANES (a quién van los wrong): Billy Estelar x4
```

- **Si el top-1 baja o aparece un imán nuevo** → alguna ref quedó mal etiquetada. Sacala con
  `tools\clean_lib_refs.py --grid "<PJ>"` y volvé a cosechar ese PJ solo.
- Los 4 `Billy Estelar` son un límite conocido, no una regresión: Billy y Billy Estelar son el
  mismo personaje con distinto atuendo (ver §7 del
  [Dev_IA](./Dev_IA/2026-08-02_FIX_Colapso_Librerias_Badges.md)).

Y la salud general de las tres librerías:

```bash
.venv\Scripts\python.exe tools\audit_badge_lib.py
```

> El `--against-labeled` mide **badges reales contra la librería que carga la app**. No uses el
> leave-one-out para esto: mide un `.npz` contra sí mismo, así que a una librería rota le da
> perfecto. Es exactamente lo que escondió el colapso de julio.

---

## 5. Snapshot — el paso que la gente olvida

Las librerías viven en `%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\`, que **no está versionado**, y ya
se vaciaron dos veces. Si no dejás snapshot, la próxima vez perdés la cosecha entera.

```powershell
$ts = Get-Date -Format "yyyyMMdd"
Copy-Item "$env:LOCALAPPDATA\DaniBOD_ZZZ_Analytics\avatar_badge_v2.npz"    "audit\avatar_badge_v2_snapshot_${ts}_roster50.npz"
Copy-Item "$env:LOCALAPPDATA\DaniBOD_ZZZ_Analytics\avatar_row_v2.npz"      "audit\avatar_row_v2_snapshot_${ts}.npz"
Copy-Item "$env:LOCALAPPDATA\DaniBOD_ZZZ_Analytics\avatar_detbadge_v2.npz" "audit\avatar_detbadge_v2_snapshot_${ts}.npz"
```

Después **actualizá el puntero** en `app/core/agent_identifier.py::_BASELINES` a los archivos
nuevos, y commiteá los `.npz` junto con ese cambio. Eso es lo que hace que, si la carpeta del
runtime se vuelve a vaciar, la app se reponga sola con un WARNING en el log en vez de quedarse
nombrando con arte `-ico`.

> Hay un test que lo cuida: `test_los_baselines_versionados_existen` falla si el puntero apunta a
> un archivo que no está en `audit/`. Una red de emergencia imaginaria no falla al declararla —
> falla el día que hace falta.

---

## 6. Checklist TL;DR

```
□ 1. El PJ existe en `agents` con su nombre canónico (Onboarding_Nuevo_PJ §3)
□ 2. Equipado: 6 discos + W-Engine
□ 3. Screenshot de su pantalla de Equipamiento → carpeta 03_Pantalla_Agente_Discos_Equipados
□ 4. preseed_badge_lib --surface row --source frame --frame <png> --label "<PJ>"
□ 5. qa_launch -FromSource -ReadOnly -BadgeHarvest -IdDiag
□ 6. Menú de personajes → el PJ → Equipamiento → los 6 slots, unos segundos cada uno
□ 7. measure_badge_lib --against-labeled --surface grid  → que NO empeore
□ 8. Snapshot de las 3 librerías a audit/ + actualizar _BASELINES + commit
```

---

## 7. Si algo no sale

| Síntoma en el log | Qué significa | Qué hacer |
|---|---|---|
| `grid_votes=[-]` siempre, nunca aprende | el ancla no tiene nombre | volvé a entrar **desde el menú** — el latch se siembra ahí |
| `ancla decía 'X' pero el badge dice 'Y'` | el cross-check desautorizó al ancla | si Y es correcto, el ancla estaba mal; si Y es incorrecto, hay una ref envenenada → `clean_lib_refs` |
| `el recorte del badge no salió` / `queda PENDIENTE` | Hough no cerró en ese frame | normal, es intermitente — quedate en el disco y se cobra solo |
| identifica al PJ como **otro** en su propia pantalla | le falta ref de `row` | §2 |
| identifica bien pero los discos salen "dueño incierto" | le falta ref de `grid` | §3 |
| el dueño del **arma** no sale | le falta ref de `detail` | §3 — el arma usa `detail`, no `grid` |

---

*Ver el detalle técnico y las mediciones en
[`Dev_IA/2026-08-02_FIX_Colapso_Librerias_Badges.md`](./Dev_IA/2026-08-02_FIX_Colapso_Librerias_Badges.md).*
