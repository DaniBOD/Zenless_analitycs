# El atributo principal de un W-Engine dice cuál es

**2026-09-18 · FIX · migración 37**

> Lo destapó el [censo de la Fase 4](2026-09-17_QA_El_censo_que_por_fin_cierra_y_los_17_que_no_estaban.md):
> el único engine fuera de catálogo era el de Claret, y la línea del log decía `ATK base 297`.

## 1. El problema

`parser_weapon_s26` leía el atributo principal de un W-Engine tomando **el número de esa fila por
posición**, sin leer nunca la etiqueta, y lo guardaba en un campo llamado `atk_base`. La columna
`weapons.atk_base` y la línea del log (`ATK base N`) arrastraban la misma suposición.

Funcionó dos meses porque las 40 capturas del corpus dicen todas **"Ataque Base"**. La captura de
Daniel del engine de Claret (`Fortuna felina` = Catty Luck, `Engine_vista_detallada_pj/Ejemplo_50`)
dice:

> **Atributo principal: `Defensa Base` 297**

Un valor de DEF guardado y mostrado como ATK, **con las `notas` vacías**. Es la cuarta vez que
Claret destapa la misma forma: una especialidad nueva trae vocabulario nuevo y el sistema lo
rotula mal sin avisar (rol → `ATK_DPS`, afiladura → Recarga de Energía, y ahora esto).

**Atenuante medido:** `atk_base` no aparece en `scoring.py` ni en el optimizador. El daño era a lo
que el sistema *dice*, no a lo que calcula.

## 2. Medir antes (A1)

Antes de tocar nada corrí el parser sobre la captura y miré las líneas crudas del OCR:

```
Ejemplo_50: ['Fortuna felina', 'Nivel 50/50', ..., 'Defensa Base', '297', ...]   atk_base=297  notas=[]
Ejemplo_29: ['Uitima cena',    'Nivel 60/60', ..., 'Ataque Base',  '594', ...]   atk_base=594  notas=[]
```

La etiqueta **estaba ahí, limpia**, en la columna izquierda — exactamente como el atributo
avanzado, que sí la leía. El arreglo replica un patrón que ya existía en el mismo archivo.

(De paso: acá el nombre sale bien, `'Fortuna felina'`. El `Fortunafelina -01+` del censo viene del
camino de S30, no de éste. Queda anotado aparte.)

## 3. El cambio

| capa | antes | ahora |
|---|---|---|
| `WeaponParsed` | `atk_base` | `stat_base_valor` + `stat_base_tipo` (`"ATK"` / `"DEF"` / `None`) |
| parser | número por posición | + la etiqueta, sobre la **fila entera** |
| etiqueta desconocida | — | tipo `None` + nota `stat_base_tipo_no_leido`, **el número se conserva** (B2) |
| `weapons` (mig 37) | `atk_base` | `stat_base_valor` + `stat_base_tipo` |
| log | `ATK base 297` siempre | `DEF base 297`, y `¿? base` si no se leyó |
| UI de Armas, reporte del censo, firmas de dedup, `tools/` | `atk_base` | los dos campos |

**Verificado sobre el corpus entero:** 41/41 fixtures leen la etiqueta — 40 `ATK` y el de Claret
`DEF` — sin una sola abstención.

### El backfill de la migración 37, y por qué no es inventar

Las 60 filas del catálogo son anteriores a 3.2 y **ninguna es de especialidad Armero** (la única
con DEF base conocida), y 40 están verificadas directamente contra su captura. Se marcan `'ATK'`
**sólo donde hay valor**: las 10 sin número quedan sin tipo, porque un rótulo sobre un número que
no tenemos no afirma nada. El smoke check verifica el invariante: **el tipo está exactamente
cuando está el valor**.

## 4. Lo que encontraron los sabotajes

Seis sabotajes, **6/6 en rojo** al final, con el hash del diff idéntico antes y después. Pero la
primera tanda dio **tres verdes**, y cada uno enseñó algo distinto:

**Verde 1 — un bug de verdad.** El sabotaje "el fallback para líneas fundidas pierde el tipo" pasó
en verde. Formulé una hipótesis y la probé con un caso antes de tocar código: si el OCR funde
`"Defensa Base 297"` en una línea y esa línea cae en la **columna del valor**, el número se lee por
el camino normal, el fallback nunca corre, y **el tipo se pierde con la etiqueta en la mano**:

```
fundida a la IZQUIERDA : (297, 'DEF', [])
fundida a la DERECHA   : (297, None, ['stat_base_tipo_no_leido'])
```

No era silencioso (la nota estaba), pero se abstenía teniendo el dato. Arreglado, con un test que
recorre las dos columnas.

**Verde 2 y 3 — protecciones que ningún test miraba.** La UI podía dejar de pasar el tipo y el log
podía volver a decir "ATK" siempre, y todo seguía verde. Se agregaron los dos tests.

**Y un verde que apareció DESPUÉS del arreglo, y era información.** Al sacar la búsqueda del tipo
fuera del `if`, el sabotaje "el parser deja de leer la columna de la etiqueta" pasó a verde:
la búsqueda sobre la fila entera **ya cubría** la columna izquierda. Quedaron dos caminos haciendo
lo mismo. Se borró el redundante — **un sabotaje en verde no siempre pide un test más; a veces
pide código de menos** (B1).

## 5. La guarda que ningún fixture ejercita

`_ATK_MAX_POR_RAREZA` deduce la rareza a partir del ATK base como corroboración del badge. Se agregó
la guarda "sólo si el tipo es ATK" — un DEF que cayera en el rango de un ATK inventaría una
discrepancia.

Pero **ningún fixture produce esa colisión** (el único de Armero vale 297, fuera de la tabla): sobre
el corpus, la guarda se puede borrar y todo sigue verde. Una protección que ningún test puede
tumbar no está verificada, sólo escrita. Se extrajo a una función pura,
`corroborar_rareza_por_atk`, con 5 tests propios que sí la rompen.

**El costo, dicho:** una especialidad nueva estrena con **una sola señal** de rareza (el badge).
No se corrobora con una tabla que no es suya.

## 6. Errores míos en el camino

- **Apliqué la migración con la app abierta.** Escribí `chequeo && aplicar`: el chequeo imprimió
  *"APP CORRIENDO — no aplicar"* y el `&&` aplicó igual, porque el comando del chequeo terminó con
  éxito. **Encadené una verificación con la acción que esa verificación tenía que poder frenar.**
  Sin daño —el monitor estaba detenido desde el cierre del censo, y `integrity_check` y
  `foreign_key_check` dieron ok—, pero fue suerte, no método.
- **Un heredoc de bash rompió los `\n` escapados** de un script de sabotaje, exactamente lo que la
  regla de trabajo advierte. Se reescribió con la herramienta de escritura.
- **Un rename a medias en la UI**: el `SELECT` pasó a devolver 15 columnas y el unpacking seguía
  con 14 nombres. Lo atraparon 14 tests de la pantalla Armas antes de llegar a commit.

## 7. Dos sesiones sobre el mismo repo

Mientras corría la suite completa de este arreglo, **otra sesión aplicó la migración 38**
(enemigos y Shiyu) sobre la misma DB. El sha pasó de `9ecff316` a `b7dbab02` a mitad de corrida, y
la suite terminó con 2960 passed y **un ERROR**: la guarda de sesión, *"algún test escribió en la
DB de dominio"*.

Era falso: no escribió un test, escribió otro proceso. Y el consejo que imprime la guarda —
`git checkout -- db/danibod_zzz_v2.db`— **habría borrado las migraciones 37 y 38**. La guarda no
puede distinguir las dos causas y su remedio es destructivo justo en la que no contempla. Queda
anotado; no se tocó.

Compartimos árbol de trabajo **e índice de git**, con archivos que tenían cambios de las dos (la
DB, el índice de Dev_IA, `Modelo_Relacional`). Se coordinó por mensaje: esta migración va primero y
la 38 después, cada commit con **la DB exacta de su migración**. El backup que dejó la otra sesión
antes de la 38 resultó ser byte a byte el estado que vio esta suite al arrancar (`9ecff316`), así
que el commit de la 37 se armó con ese blob por plumbing (`git hash-object` + `update-index
--cacheinfo`) sin tocar ningún archivo ajeno del árbol. La suite que vale como compuerta se corrió
de nuevo, con la otra sesión ya sin escribir.

## 8. Después: el alta de Fortuna felina (migración 39)

El engine de Claret entró al catálogo **después** de este arreglo a propósito, para estrenarlo con
el atributo principal ya rotulado (`stat_base_tipo = 'DEF'`, `tipo_especialidad = 'Armero'`).

**Dos fuentes para cada valor**, más la pantalla: Gachabase 13017 con `lang=es` da el nombre en
español **idéntico** al de la pantalla (*Fortuna felina*) y Game8 el inglés (*Catty Luck*); las dos
coinciden en Defensa Base **356** y DEF **40 %** a nivel 60, y en la pasiva (*Almohadillas de la
suerte* / *Lucky Pawpad*, 8 % a R1 → 12 % a R5, que es lo que muestra la pantalla a P5). Un tweet
decía 342: la única fuente que discrepa.

**La pantalla dijo 297, y ese número no entró.** El arma está a Nv 50/50 y el catálogo guarda el
valor de nivel 60 — mismo criterio que *Tetera esmeraldina* en la migración 27. Chequeo interno que
no dependía de ninguna wiki: 297/356 = **0,834**, y Tetera leyó 595 a 50/50 contra el 713 de una S
a nivel 60: **0,834**. Es la misma curva de crecimiento, sacada de datos que no se tocan entre sí.

**Una corrección a la migración 37.** Ahí llamé *invariante* a que el tipo del stat base esté
exactamente cuando está el valor. Es falso como regla: el tipo es una propiedad del arma (la
etiqueta no cambia con el nivel) y el valor del catálogo es el de nivel 60. Un arma leída sólo por
debajo del máximo tiene tipo conocido y valor NULL, y eso no miente. Lo que sí miente es lo
contrario —un número sin decir qué stat es—, y ese es el smoke check que quedó. La 37 no se
reescribe; la corrección vive en la 39.

**Lo que la 39 NO hace:** no inserta la fila de inventario. La escribe la app la próxima vez que
pase por S30 (decisión de Daniel: el flujo normal). El nombre roto de S30, `Fortunafelina -01+`,
**ya matchea** el catálogo por el fuzzy — verificado con `match_catalogo` contra el catálogo real —,
así que el `-01+` pasa de bug bloqueante a cosmético.

El ícono estaba sólo en `claude_design_upload/`, que está gitignoreada y que un script borra; se
copió a `app/resources/ui_assets/Engines_icons/` (D1) y a `Assets_Originales/w_engines/`. Resuelve
**por el nombre inglés**: sin `nombre_en` en la fila, `engine_icon_path` se abstiene. Por eso el
nombre inglés no era un dato decorativo.

**Tests y sabotajes:** 4 tests sobre lo que la fila habilita (no sobre que exista). 5 sabotajes, 5
rojos. Los cuatro que rompen la fila se hicieron sobre una **copia descartable** de la DB —
apuntando el test a ella—, nunca sobre la real (B3); el sha de la real quedó igual.

Otra vez dos sesiones: la DB del árbol tiene la 38 sin commitear. La 39 se aplicó **dos veces**:
sobre una copia de la DB de `HEAD` (esa es la que va al commit, con la 37 y la 39 pero sin la 38) y
sobre la del árbol (que conserva las tres).

De paso: el `--dry-run` del runner de migraciones abre su propia transacción y choca con el
`BEGIN TRANSACTION` que tienen **todas** las migraciones del repo. El ensayo se hizo aplicando de
verdad sobre una copia descartable.

## 9. Pendiente

- **El `-01+` que agrega el camino de S30** al nombre: ya no bloquea (matchea igual), pero es basura
  en el log.
- **La fila de inventario de Claret** entra en la próxima pasada por S30.
- **Declarar alcance en el censo de armas**, o va a reportar un hueco para siempre.
- **`Modelo_Relacional/README.md`** no documenta todavía `weapons.stat_base_*`: la otra sesión lo
  estaba editando y no se tocó para no pisarla. Va en un commit aparte.
- **La guarda de la suite** debería al menos no recomendar `git checkout` a ciegas (§7).
- **El `--dry-run` de `apply_migration.py`** no funciona con ninguna migración del repo (§8).
