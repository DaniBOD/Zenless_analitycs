# El censo que por fin cierra, y los 17 que no estaban

**2026-09-17 · Fase 4 de la hoja de ruta del log en S9 · QA en vivo + migración 36**

> Cierra la [Fase 3](2026-09-17_FIX_El_nivel_0_y_no_lo_lei_eran_el_mismo_dato.md) respondiendo
> su pregunta abierta, y la deuda que dejó el
> [QA del censo del 2026-08-30](../2026-08/2026-08-30_QA_Censo_de_discos_cinco_hallazgos_y_una_forma_repetida.md).
> Evidencia operativa completa en `audit/censo_discos_20260917.md`.

## 1. Lo que pasó

Pasada en vivo de Daniel sobre los **380 discos** del inventario, con la app **escribiendo**
(primera vez a esta escala). Resultado:

```
[censo-discos] resumen de la sesión — 380/380 registrados · 311 con dueño · 69 libres · 0 sin resolver
```

**Es la primera pasada que cierra**, y el censo de agosto tenía demostrado que no podía: calculaba
su propia identidad, el OCR leía el nombre del set distinto entre pasadas (`Firmamento Ilameante`
vs `llameante`) y el total era inalcanzable **por diseño** — se preveían ~317 de 339. Lo que cambió
no fue el OCR: fue que la identidad pasó a ser **la fila que tocó la persistencia**. Una autoridad
en vez de dos.

## 2. La verificación no la dio el número, la dio que dos números coincidieran

Que el censo diga 380/380 por sí solo no prueba nada: es un contador comparándose con otro
contador. Lo que cierra el caso es que **la persistencia tocó 380 filas distintas**. Son dos
caminos independientes —contar discos en pantalla y contar filas en la DB— dando el mismo número,
y eso significa **biyección**: cada disco encontró su fila y ninguna fila se usó dos veces.

Y salió un cruce que nadie construyó: el censo contó **69 libres**, la DB tenía **86**. La
diferencia es **17**, exactamente las filas que la pasada no vio.

## 3. Por qué acá sí se puede borrar por ausencia

La regla es que **la ausencia no prueba la inexistencia** (B2). Lo que la habilita es el
**criterio de completitud**, y es la primera vez que se cumple: si se tocaron tantas filas como
discos hay en pantalla, lo que quedó afuera no está en la pantalla.

Las 17 dadas de baja (migración 36) son **todas libres, no equipadas y vigentes**, 13 en Nv0, 2 en
Nv3 y 2 en Nv15 — el perfil exacto del descarte de farmeo, y Daniel confirmó que estuvo
desmontando. Ninguna estaba referenciada en `inventory_disc_evaluations`.

**Sobre los repetidos:** entre las 17 hay 4 filas idénticas y 3 idénticas. Preguntar *cuál* borrar
no tiene sentido — son indistinguibles en todo campo observable, así que borrar unas u otras es la
misma operación. Lo que la evidencia sostiene es el **número**.

## 4. La respuesta que habilitó la Fase 3

| de los 23 discos en Nivel 0 | |
|---|---|
| se volvieron a ver | **10** |
| **siguen en Nivel 0** | **10** ← genuinos |
| eran mala lectura del OCR | **0** |
| no aparecieron (desmontados) | 13 |

**El Nivel 0 era real en todos los casos verificables.** La sospecha de partida —"esos 23 son
lecturas fallidas"— era falsa. Y el punto no es que me equivoqué: es que **antes de la Fase 3 la
pregunta no se podía hacer**, porque el 0 significaba las dos cosas. Separar "no lo leí" de "Nivel
0" no arregló un número: hizo la pregunta formulable.

En toda la pasada hubo **0 filas con nivel NULL y 0 marcadas**: el nivel se leyó en los 380, y la
contra que la Fase 3 anunció (el ~13 % esperando el techo de ciclos) **no se materializó**.

## 5. El censo de armas: el mismo mecanismo, la respuesta opuesta

`53/69 registradas · 47 con dueño · 1 sin resolver · 1 fuera de catálogo · 0 filas nuevas`

Los 16 que faltan son los W-Engines de **rango B que Daniel decidió no censar**. El sistema no
podía saberlo: dijo *"o no se recorrieron, o son copias que no pude localizar"* y **se negó a
elegir**. Esa información la tenía el usuario.

Y por eso mismo, acá la ausencia **no prueba nada**: hay 7 filas sin tocar que no se pueden juzgar,
y dos son pares repetidos (`Cámara acorazada` ×2, `Transmorfer original` ×2) — justo el caso que el
reporte avisa que cuenta de menos. **Mismo mecanismo, criterio no cumplido, conclusión opuesta.**
Es la mejor demostración de que el criterio de completitud es lo que hace la diferencia, no el
mecanismo.

⚠️ **Y tal como está, el censo de armas no puede cerrar nunca**: el contador incluye los B y Daniel
no los quiere censar, así que siempre va a reportar un hueco. Es exactamente la condición
inalcanzable que el censo de agosto advirtió que no hay que aceptar. **Hace falta poder declarar un
alcance** para que el denominador sea honesto. Sin implementar.

## 6. Lo que la pasada destapó de yapa

### El engine de Claret: la cuarta vez que una especialidad nueva se rotula mal en silencio

El único "fuera de catálogo" fue `Fortunafelina -01+` · A · Nv 50/50 · P5 · **ATK base 297** ·
DEF% 35,2 % — y el sistema le acertó el dueño solo (Claret Flint).

La captura de la ficha (`Engines_Triggers/Engine_vista_detallada_pj/Ejemplo_50.png`, local) dice:

> **Atributo principal: `Defensa Base` 297**

`parser_weapon_s26` toma el número de esa fila **por posición y nunca lee la etiqueta**, y lo
guarda en un campo llamado `atk_base`. Es un valor de DEF con nombre de ATK, afirmado con
confianza. El nombre además salió con un sufijo inventado (`-01+`): en pantalla es `Fortuna
felina`.

Tercera y cuarta repetición de la misma forma que trajo Claret: el rol cayendo a `ATK_DPS`, la
afiladura metiéndose en Recarga de Energía, el DEF base vestido de ATK, y el nombre con basura.
**Una especialidad nueva trae vocabulario nuevo, y el sistema lo rotula mal sin avisar** (D2).

Atenuante medido: `atk_base` **no alimenta ningún cálculo** (no aparece en `scoring.py` ni en el
optimizador). Se usa para mostrar, para el reporte del censo y para el audit. El daño es a lo que
el sistema *dice*, no a lo que calcula.

Efecto lateral: `_ATK_MAX_POR_RAREZA` **deduce la rareza a partir del ATK base**. Un engine de
Armero nunca va a caer en esa tabla, así que esa vía de corroboración queda muerta para toda una
especialidad — y el corpus de 40 fixtures es **todo de "Ataque Base"**, así que un test escrito
sobre él pasaría en verde con el bug puesto. `Ejemplo_50` es el único que puede romperlo.

### Harumasa ↔ Antón

Daniel lo reportó en vivo y el log lo confirma: `id=355` pasó Harumasa→Antón a las 22:46:57 y
volvió Antón→Harumasa a las 22:47:50 (`s17_move`, "corrección tardía"). **Se autocorrigió** y los
dos terminan 6/6. 3 `DESPLAZADO` en la pasada. Sin tocar, por pedido de Daniel.

### La latencia empeoró y no sé por qué

`click→log` p50 **3391 ms** en esta ventana, contra los **2562 ms** con los que cerró la Fase 2.
Las dos explicaciones cómodas **no aguantan**: la persistencia mide 16-47 ms (no es "ahora
escribe") y el OCR del panel está **más rápido** (p50 618 ms contra 1608 ms). Lo que creció es el
`detector` (p50 595 ms) y el `loop_period` (p50 1187 ms contra ~391 ms).

**Sin diagnosticar**, y la comparación **no es limpia**: la Fase 2 midió una pasada controlada de
~10 discos y esto son 124 muestras de una pasada larga con dos relevos del worker de OCR en el
medio. Se anota para medirlo aparte, no para concluir nada.

## 7. Estado

| | antes | después |
|---|---|---|
| filas totales | 403 | **386** |
| vigentes | 397 | **380** ← el contador de pantalla |
| con dueño | 311 | 311 |
| libres | 86 | **69** |
| Nivel 0 vigentes | 25 | **12** (10 genuinos + 2 farmeados en la pasada) |
| PJs con los 6 slots | **43/51** (agosto) | **51/52** |

Migración 36 con 7/7 smoke checks exactos, `foreign_key_check` sin filas, `integrity_check` ok.
Suite completa **2938 passed / 0 failed / 0 skipped**.
