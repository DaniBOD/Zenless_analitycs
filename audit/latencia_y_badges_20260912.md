# Latencia del inventario de armas + cosecha de badges (2026-09-12, 02:15-02:22)

Corrida con `qa_launch.ps1 -FromSource -Metrics -IdDiag`. **1587 muestras** en `db/metrics.db`
(DB aparte: no toca la de dominio). Ventana 02:14:55 → 02:22:31, con 599 ciclos del loop.

## 1 · Latencia: el costo está en el CICLO del inventario, no en el reconocimiento de pantalla

`report_latency --dias 1`, contra los presupuestos de QA-06 §3.1:

| superficie | n | p50 | p99 | máx | presupuesto | veredicto |
|---|---|---|---|---|---|---|
| `capturer` | 599 | 46 ms | 59 ms | 378 ms | 50 | al borde |
| `detector` (classify) | 599 | **191 ms** | 598 ms | 1863 ms | 50 | **4× el presupuesto** |
| `ocr_text` (por llamada) | 251 | 122 ms | 980 ms | **12511 ms** | 180 | cola larguísima |
| `dispatch:S30` | 71 | **1569 ms** | 2709 ms | 2709 ms | 1500 (su cadencia) | **saturado** |
| `dispatch:S26` | 18 | **2679 ms** | 4404 ms | 4404 ms | 1000 | **saturado** |
| `dispatch:S15` | 34 | 0.4 ms | 639 ms | 639 ms | 1000 | ok |
| `dispatch:S8` | 4 | 3 ms | 5 ms | 5 ms | 1500 | ok |

Suma coherente con lo que se ve en el log: captura 46 + classify 191 + handler 1569 ≈ **1,8 s**,
que es el ciclo de ~2 s que reporta el heartbeat (30 ciclos/min en S30). La cadencia configurada
(1500 ms) **no es la palanca**: el procesamiento ya la excede y el sleep es cero.

### Dónde se va el tiempo DENTRO del handler (medido offline, 5 capturas × 3 corridas)

| etapa | mediana |
|---|---|
| firma del panel | 1 ms |
| ubicar la selección en la grilla | 12 ms |
| **parsear el panel (OCR)** | **468 ms** |
| badge del dueño + match contra 105 refs | ~0 ms adicionales |
| contador del header (cadencia propia) | 47 ms |

**El hallazgo:** las etapas suman ~480 ms y el handler mide **1569 ms** en la app. Sobran ~1,1 s
que NO están en el parseo. La diferencia entre las dos mediciones es que la app manda el OCR a
**otro proceso** (`ocr_service`), así que el sospechoso es el ida y vuelta con el worker — pero
**no está probado**, y este proyecto ya pagó caro atribuir latencia por razonamiento (el sleep que
era 0 % en el censo de discos).

**Sospecha descartada:** el OCR del título en cada `classify` (`_read_inventory_header`) se creía
el costo principal. Es real —191 ms de p50 contra 50 de presupuesto— pero es **un octavo** del
ciclo, no la causa.

### Lo que recomiendo medir antes de optimizar

1. **Partir `dispatch:S30` en sub-bloques** con `metrics.measure_block` (parseo / badge / censo /
   persistencia). Es instrumentación, no optimización, y resuelve los 1,1 s sin adivinar.
2. **La cola de `ocr_text`**: p50 122 ms contra un máximo de **12,5 s** (02:15:08). Ese pico
   coincide con el relevo del worker de OCR por techo de memoria. Vale la pena confirmarlo:
   si el relevo bloquea la llamada en curso, el usuario ve un congelamiento de 12 s.
3. **`capturer` al borde** (p50 46 contra 50 ms) — no es urgente, pero cualquier mejora del ciclo
   lo deja como el siguiente techo.

### Bug de instrumentación, aparte

`frescura_estado_a_log` registra **1.789×10¹⁵ ms**: está guardando un timestamp absoluto como si
fuera una duración. La métrica no sirve hasta arreglar eso, y no mide lo que dice medir.

## 2 · Cosecha de badges: funcionó para Billy y Zhao

La librería del detalle pasó de **103 a 105 refs** (`avatar_detbadge_v2.npz`, mtime 02:19:24):
`Billy` 1 → 2, `Zhao` 2 → 3.

| | antes | después |
|---|---|---|
| Réplica de motor estelar | top `Ben 0.422`, margen 0.027 ⇒ **abstenía** | top `Billy 0.172`, margen 0.250 ⇒ **la tiene Billy** |
| Transmorfer original | top `Zhao 0.306`, margen 0.029 ⇒ **abstenía** | top `Zhao 0.120`, margen 0.215 ⇒ **la tiene Zhao** (fila 56) |

El camino que las cosechó es el de `_maybe_harvest_weapon_owner`: ficha del PJ → arma → botón
*Desequipar*, con el latch confirmando el nombre (`[cosecha] detalle-badge de 'Billy' desde el
arma 'Réplica motor estelar'`). **No hubo vetos.**

## 3 · CERRADO el mismo día: era una ref MAL ETIQUETADA

> Lo de abajo quedó como historia del diagnóstico. El desenlace: la única ref vieja de la clase
> `Billy` era **la cara de Billy Estelar**. Medido ref por ref contra el badge de Estelar
> (`Ejemplo_18`): esa ref daba **0.156** y la de Billy **0.475**; como la distancia de una clase es
> la de su MEJOR ref, Billy le ganaba a Estelar en el arma de Estelar.
>
> **Cómo se destapó:** la cosecha guiada de Billy Estelar salió `veto_conflicto` — el juego decía
> "Billy Estelar" (botón *Desequipar*) y el matcher afirmaba "Billy" a 0.09. La guarda evitó
> aprender la cara bajo la etiqueta equivocada, y ese veto fue la pista.
>
> **Arreglo:** la ref se MOVIÓ a `Billy Estelar` (no se borró; backup
> `avatar_detbadge_v2.backup_prerelabel_20260912_024322.npz`). Verificado releyendo la librería en
> un proceso limpio: `Ejemplo_17` → Billy 0.172 (margen 0.250), `Ejemplo_18` → Billy Estelar 0.156
> (margen 0.272). Snapshot para los tests:
> `audit/avatar_detbadge_v2_snapshot_20260912_billy_estelar.npz`; los 35 tests de verdad de tierra
> pasan y ya no queda ningún `xfail`.
>
> **Dato:** la fila 26 se reasignó a Billy Estelar (mig `_30`). La `Réplica` de Billy sigue sin
> escribirse: la tiene que ver una pasada, que ahora ya no choca con nada.
>
> **Dos hipótesis mías cayeron antes de dar con esta**, y la segunda la descarté con una medición
> equivocada: comparé las refs con una distancia L2 sobre la imagen en gris en vez de la métrica
> del matcher, y concluí que la ref vieja no se parecía a Estelar. Con la métrica correcta era
> justo la que atraía. **La lección: medir con la métrica que usa el sistema, no con una parecida.**

### El diagnóstico, como quedó escrito antes de cerrarlo

Daniel confirmó que `Tránsito herciano` es de **Billy Estelar**, y el sistema la atribuyó a
**Billy** (fila 26):

    top=Billy:0.16, Billy Estelar:0.26, Pyrois:0.43 → margen 0.10 → "la tiene Billy"

**No son el mismo personaje ni un atuendo:** en `agents`, Billy es id 12 (rango A, Ataque, M6) y
Billy Estelar es id 47 (rango **S**, **Disruptivos**, M0), y cada uno tiene sus 6 discos.

Dos hipótesis mías ya cayeron, medidas:

- *"La ref vieja de Billy es en realidad la cara de Estelar y roba los matches"* — **falso**. Ref
  por ref contra la Réplica: `Billy #1` (la nueva) 0.172, `Billy #0` (la vieja) 0.491.
- *"A Billy le faltaban refs"* — cierto sólo para la Réplica; para Tránsito el problema es otro.

Lo que queda por decidir con evidencia: si las 3 refs de `Billy Estelar` son viejas (encuadre
previo al 2026-08-14) y por eso dan 0.26, o si las dos caras son genuinamente parecidas a 42 px.
**Pide una captura de `Tránsito herciano` seleccionada en S30** y una cosecha guiada de Billy
Estelar, igual que la que resolvió a Billy y a Zhao.

### Efecto en los datos, hoy

- Fila 26: `Tránsito herciano` figura con **Billy** y debería ser de **Billy Estelar**.
- La `Réplica de motor estelar` **no se escribió**: el bucket B se abstuvo con un warning explícito
  porque Billy ya figuraba con otra arma. **La abstención fue correcta** — una de las dos lecturas
  estaba mal y el sistema no podía saber cuál.
- Corrección pendiente (con backup y ensayo sobre copia): reasignar la fila 26 a Billy Estelar, y
  recién entonces una pasada escribe la Réplica para Billy.
