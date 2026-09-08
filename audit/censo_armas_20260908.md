# Censo de W-Engines — primera pasada en vivo (2026-09-08)

**Reconstruido del log, no del reporte de cierre.** La pasada terminó parando el monitor y no con
F8, así que `cerrar_censo_armas()` nunca corrió y el `resumen()` se perdió. Los números de acá
salen de `app.log` entre las 11:43 y las 11:54. Ver "Deuda" al final.

**Alcance:** sólo los tiles de rango **S y A**, por decisión de Daniel. Los B quedan para otra
pasada, así que la cobertura contra el contador del header es parcial por diseño.

## Números

| | |
|---|---|
| identidades censadas | **53** de las **185** que declara el header |
| filas escritas en `inventory_weapons` | **28** (la tabla tenía 0) |
| PJs cubiertos | 28 de 51 |
| fuera de catálogo | 15 lecturas ≈ 7 armas distintas |
| con dueño presente pero sin nombrar | 11 lecturas |
| conflictos descartados | 9 |
| `integrity_check` / `foreign_key_check` | ok / limpio |

Backup previo a la pasada: `db/danibod_zzz_v2.backup_premig_20260908_114314.db` (lo hizo
`tools/qa_launch.ps1`).

## Las 28 filas

| id | arma | PJ | nivel | refin. |
|---|---|---|---|---|
| 1 | Engranaje infernal | Dialyn | 60 | P2 |
| 2 | Petrazufre | Sporos | 60 | P1 |
| 3 | Visitante de altamar | Ellen | 60 | P1 |
| 4 | Esplendor surcanimbos | Ye Shunguang | 60 | P1 |
| 5 | Sol exuvia | Pyrois | 60 | P1 |
| 6 | Coctelera incandescente | Burnice | 60 | P1 |
| 7 | Aguijón agudo | Jane | 60 | P1 |
| 8 | Motor estelar | N.º 11 | 60 | P5 |
| 9 | Florescencia aurífera | Antón | 60 | P5 |
| 10 | Amo de llaves | Corin | 60 | P5 |
| 11 | Taladradora giratoria - Eje rojo | Cissia | 60 | P5 |
| 12 | Rotor de cañón | Evelyn | 60 | P5 |
| 13 | Última cena | Gatillo | 60 | P5 |
| 14 | Fósil preciado | Nangong Yu | 60 | P5 |
| 15 | Caldero ardiente | Ju Fufu | 60 | P5 |
| 16 | Gastrónomo selvático | Piper | 60 | P5 |
| 17 | Llanto mielgo | Aria | 60 | P5 |
| 18 | Ecos bulliciosos | Velina | 60 | P5 |
| 19 | Lapso de tiempo | Rina | 60 | P5 |
| 20 | Cámara acorazada | Nicole | 60 | P5 |
| 21 | Demonio cohibido | Astra Yao | 60 | P5 |
| 22 | Cañón bombástico | Lucía | 60 | P5 |
| 23 | Proyector de celuloide | César | 60 | P5 |
| 24 | Pacificador especializado | Seth | 60 | P5 |
| 25 | Rompecabeza ilusorio | Manato | 60 | P5 |
| 26 | Tránsito herciano | Billy | 60 | P5 |
| 27 | Caldero de la claridad | Yixuan | 60 | P5 |
| 28 | Primavera termal | Pan Yinhu | 60 | P2 |

Todas con `origen_evidencia='s30_badge'` y `equipado=1`.

## Los 9 conflictos — y por qué el bucket C estaba mal

Cada uno es un arma que ya figuraba equipada por otro PJ. La v1 los descartaba leyéndolos como
"una de las dos lecturas del badge está mal".

| arma | copias leídas |
|---|---|
| Cañón bombástico | Lucía P5 · Yuzuha P5 · **Sunna P3** |
| Rotor de cañón | Evelyn P5 · **Zhu Yuan P2** |
| Última cena | Gatillo P5 · Koleda P5 · Lycaon P5 |
| Llanto mielgo | Aria P5 · Alice P5 · Yanagi P5 · Vivian P5 · Remielle Dan P5 |

**El refinamiento es un discriminador independiente del badge**, y ahí está la prueba: un badge mal
leído sobre el mismo tile mostraría el MISMO refinamiento. Que Sunna dé P3 contra los P5 de Lucía y
Yuzuha, y Zhu Yuan P2 contra el P5 de Evelyn, sólo se explica con piezas físicas distintas. La
fungibilidad no es una interpretación: está medida.

Para 'Última cena' y 'Llanto mielgo' **no hay discriminador** — todas P5 — así que no se pueden
probar por esta vía. Que el mecanismo exista sube mucho la probabilidad, pero 'Llanto mielgo' en
cinco PJs es el caso que más conviene mirar contra la pantalla antes de darlo por bueno.

Arreglado en `6f1a1cb`: C inserta como fila nueva con trigger `s30_insert_copia`. Las 9 se
recuperan en la segunda pasada, que es barata porque el bucket A convierte cada relectura en un
`update`.

## Fuera de catálogo — entrada de la migración curada

Nombre español **leído de pantalla**, que es el dato que ninguna wiki da. Ninguna se da de alta
sola (RNF-02): la migración se revisa a mano.

| nombre crudo | notas |
|---|---|
| Anhelomarcato DESRE | de Orfia y Magas |
| Cilindroneumatico de Bigger | de Ben; leído también como `Cilindroneumätico` |
| Inocencia sacrificada | de N.º 0: Anby; leído también como `X Inocencia sacrificada` |
| Temploala granizadaestelifera | de Miyabi |
| Tetera esmeraldina | de Qingyi |
| Viajeestruendoso CRASH | |
| ~~X Cuter~~ | **FALSO — es `Cúter`, de Pulchra, y está en el catálogo.** Ver la corrección de abajo |

> ⚠️ **Corrección (misma fecha, tras la segunda pasada).** La frase que estaba acá —*"el prefijo `X `
> no es el motivo del rechazo, las dos faltan de verdad en `weapons`"*— **era falsa**, y la escribí
> sin medirla. Al probar `match_catalogo` contra las 59 filas reales, `X Cuter` resuelve a **Cúter**
> y `X Uitima cena` (de la segunda pasada) a **Última cena**. Las dos estaban en el catálogo desde
> siempre.
>
> Son **6 huecos reales, no 7**, y el costo no fue sólo un fantasma en esta tabla: son **dos filas
> de `inventory_weapons` que no se escribieron**, una de ellas la de Pulchra.
>
> Lo que ninguno de los dos casos mostraba por separado: **ningún defecto solo rompe el match.**
> `Uitima cena` (la confusión l→i) resuelve, y `X Última cena` (el glifo) también; hacen falta los
> dos en la misma lectura para caer debajo del corte de 0.84. Por eso las 10 capturas de fixture,
> que leen limpio, no lo reproducen.
>
> Arreglado en `parser_weapon_s26.match_catalogo` con un **segundo intento** sin el carácter suelto
> de la izquierda, que sólo corre si el primero devolvió None: puede agregar matches donde no había,
> nunca cambiar uno que ya resolvía. Acotado a un token de un carácter: ninguna de las 59 filas tiene
> un primer token de ≤2 caracteres, así que el recorte no puede tapar un nombre legítimo.
>
> **Segunda corrección, y esta la destapó un sabotaje.** Escribí que no aflojaba el corte *"porque
> cruzaría Modelo II con Modelo III"*. Es falso: normalizados miden **0.977** de similitud, muy por
> encima de 0.84, así que el corte nunca fue lo que los separa — los salva el match EXACTO, porque
> `_norm_nombre` colapsa los romanos ambiguos y 'Modelo ll' cae justo sobre 'Modelo II'. Con corte
> 0.70 siguen resolviendo bien. El motivo REAL para preferir el segundo intento es que aflojar el
> corte mueve toda comparación: el sabotaje midió que con 0.70 `XY Uitima cena` empieza a resolver.
> El docstring del test que afirmaba lo contrario quedó corregido también.
>
> **Sigue abierto de dónde sale la `X`.** El arreglo es de tolerancia, no de causa. La pista es que
> una de las cuatro lecturas con `X ` era el panel de la propia app; pide un frame que lo reproduzca.

## Dos hallazgos que no son del censo

### La app se lee a sí misma

Una lectura salió así:

    [S30] Inventario W-Engine — X Monitor: OFF granajeinfernal 385 305 0/385 · ? · Nv 60/60 · P2 ...

No es un arma: es **el panel de la propia app**, con su "Monitor: OFF" y los contadores de discos
`385 305 0/385`. La ventana quedó encima del juego y el OCR se la comió. Acá fue inofensivo —lo
rechazó el catálogo— pero el pipeline no tiene nada que impida leer su propia UI.

### Zhao: presencia sí, nombre no

    [S30] Transmorfer original · A · Nv 60/60 · P5 · ATK 594 · HP% 25% · con dueño (sin identificar)

Dos lecturas iguales. Daniel confirmó contra la pantalla que **es de Zhao**. El veredicto es
`con dueño (sin identificar)`, **no `LIBRE`**, y la distinción decide el arreglo:

- el `Compilador quimérico` **afirma ausencia** siendo de Grace ⇒ es el falso LIBRE, y es lo que
  bloquea escribir las armas libres;
- el `Transmorfer original` **detecta presencia y no sabe nombrar** ⇒ es la clase floja conocida de
  Zhao en la librería de badges (refs con otro encuadre). Se arregla con refs, no tocando la
  lógica de tenencia.

El sistema se abstuvo, que es lo correcto. Hay además un TERCER `Transmorfer original` (Nv 0/10,
P1, ATK 40) genuinamente libre: son piezas distintas.

## Deuda que dejó esta pasada

1. **El resumen del censo vive sólo detrás de F8.** Parar el monitor —o cerrar la app— descarta el
   censo en silencio: no hay reporte, no hay desglose, y no queda dicho que se perdió. Este archivo
   existe porque se pudo reconstruir del log; no siempre va a poder.
2. **Segunda pasada pendiente** por Última cena, Llanto mielgo, Cañón bombástico y Rotor de cañón,
   para recuperar las 9 filas con el bucket C arreglado.
3. **Los tiles de rango B** sin recorrer.
4. **Migración curada** de las ~7 armas de arriba.
5. **Refs de Zhao** para la superficie `detail`.
