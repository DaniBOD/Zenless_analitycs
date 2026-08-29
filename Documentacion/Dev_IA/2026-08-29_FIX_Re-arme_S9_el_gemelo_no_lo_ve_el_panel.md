# El re-arme de S9: lo que el panel no puede ver, y las dos hipótesis que la medición corrigió

> **2026-08-29.** Sale del plan de responsividad del censo, y **el plan estaba mal en dos puntos**.
> Los dos se cayeron con las capturas nuevas (`Ejemplo_15..18`), antes de escribir una línea de
> código de producción.
>
> Continúa [`2026-08-18_QA_Censo_Discos_en_vivo.md`](./2026-08-18_QA_Censo_Discos_en_vivo.md).

---

## 1. El síntoma, que sí era real

Pasada del censo del 2026-08-20, 119 discos en 23 minutos. Agrupando cada intervalo por si el
disco comparte set + slot + main con el anterior:

| grupo | n | mediana | p75 | p90 | max |
|---|---|---|---|---|---|
| **mismo** set+slot+main | 53 | 8,0 s | 13,0 s | **29,0 s** | 60 s |
| distinto | 65 | 7,0 s | 8,0 s | 12,0 s | 155 s |

Las medianas casi no se distinguen. **Lo que explota es la cola**, y el 45 % de los discos cae en
ese grupo.

## 2. Hipótesis 1: "el OCR no distingue los substats" — DESMENTIDA

El razonamiento era: la firma `_s9_disc_signature` mira **sólo el panel derecho** (título 48×24 +
bloque main/substats 48×48, en gris). Si el disco siguiente comparte set + slot + main, el único
diferenciador queda siendo el texto de los substats, y en 48×48 px eso casi no mueve la media.

Daniel capturó justo ese caso: `Ejemplo_17` y `Ejemplo_18`, los dos **Fábula Yunkui · slot 3 ·
DEF 184 · nivel 15**. Medido:

```
componente TÍTULO   1.38     (umbral 3.0)
componente CUERPO   6.11     ->  RE-ARMA, con 2x de margen
```

**El bug no reproduce.** Los substats sí difieren (Maestría 27 vs Perforación 18, y en otro orden)
y el cuerpo los separa de sobra. La hipótesis era falsa: cuando los substats difieren, el panel
alcanza.

### El corpus completo lo confirma, y de paso corrige el margen que yo había reportado

Con las 4 capturas nuevas son 18 fixtures, 153 pares. Un solo par cae por debajo del umbral:

| par | diff | qué son |
|---|---|---|
| Ej_12 vs Ej_16 | **2.85** | el MISMO disco, capturado dos veces |
| Ej_11 vs Ej_15 | 3.09 | el MISMO disco, capturado dos veces |
| Ej_2 vs Ej_8 | 3.66 | el par de discos **distintos** más parecido |

O sea que `Ejemplo_15` y `Ejemplo_16` son **re-capturas de los mismos dos discos** que ya estaban
en el corpus como 11 y 12 (diff del panel 1,58 y 0,77 — idénticos), pero con la grilla
completamente distinta (diff 52) porque el inventario se re-ordenó al reconstruir la DB.

Eso da algo que el corpus viejo no tenía: **el piso de ruido del mismo disco**, 2,85-3,09. El
umbral de 3,0 está *adentro* de esa banda. No es que tenga poco margen: la separación real contra
el par distinto más cercano es 3,09 → 3,66, un 18 %.

## 3. Hipótesis 2: "la posición de la selección, por diferencia de píxeles" — DESMENTIDA

El plan proponía agregar una tercera componente con la región de la grilla, comparada como las
otras dos (media de diferencias absolutas). Medido sobre los pares que son una navegación real a
un tile vecino:

| par | grilla (media) | panel (media) |
|---|---|---|
| Ej_15 → Ej_16 | **2,55** | 7,51 |
| Ej_17 → Ej_18 | **2,33** | 6,26 |

La grilla se mueve **menos** que el panel. Tiene sentido: el recuadro de selección es un cambio
muy localizado y la media sobre toda la región lo diluye. Como discriminador habría sido *peor*
que lo que ya había.

## 4. Lo que sí falla, y no depende de ningún umbral

El caso que el panel **no puede** resolver es el disco **gemelo**: mismo set, slot, main *y*
substats. Ahí el panel es idéntico pixel a pixel — la diferencia da exactamente `0.00` — y no hay
umbral posible. En el inventario real hay **22 pares** así.

No hay captura de un gemelo (habría que dar con uno de los 22 y fotografiarlo), así que el caso se
**construye**: se pega el panel derecho de `Ejemplo_17` sobre el frame de `Ejemplo_18`. El
resultado es exactamente lo que ve la app frente a un gemelo — panel idéntico, selección en otro
tile — y el test lo verifica antes de nada:

```python
assert Monitor._sig_component_diff(sig_a[0], sig_b[0]) == 0.0
assert Monitor._sig_component_diff(sig_a[1], sig_b[1]) == 0.0
```

## 5. El arreglo: localizar, no diferenciar

La pieza ya existía. `_selected_grid_tile_bbox` —lo que usa `read_s9_selected_badge` para saber de
qué tile recortar el avatar— devuelve el bounding box del tile resaltado. Se expuso como
`s9_selected_tile_pos(frame) → (cx, cy, lado)` y se agregó como tercera componente de la firma.

Es **discreta**, no un umbral sobre una media:

```
moverse a un tile vecino   ->  el centro salta ~175-183 px, sobre un tile de ~177
jitter del localizador     ->  el lado medido varía 167-177 px entre capturas
tolerancia elegida         ->  medio tile  (2x de margen contra el salto real)
```

La tolerancia sale del lado del propio tile y no de un número de píxeles, así vale a otra
resolución.

### Dos decisiones que el test fija

**`None` no decide.** En 3 de las 18 capturas no hay tile localizable. Ausencia de posición es
ausencia de dato: si eso forzara un re-arme, un frame sin selección re-armaría por no saber. La
decisión vuelve al panel, o sea a la conducta anterior a que esta componente existiera (RNF-02).

**El error se sesga a re-armar de más.** Un re-arme espurio cuesta una re-lectura de ~1 s; uno
perdido le cuesta al usuario los 20-60 s que tarda en notar que el toast no va a salir. La
asimetría es de 20x a 60x, así que el umbral se calibra para no perder cambios.

## 6. El costo, medido

Sobre los 153 pares del corpus:

```
re-armaban antes : 152
re-arman ahora   : 153
re-armes NUEVOS  : 1     (Ej_12 vs Ej_16)
re-armes PERDIDOS: 0
```

El único nuevo es el mismo disco en dos posiciones de grilla distintas — un re-arme correcto por
definición: la selección se movió. En el flujo real, dos frames consecutivos no tienen la grilla
re-ordenada.

## 7. Un bug de tipos que apareció de rebote

La primera versión hacía fallar `assert m._is_new_s9_disc(sig) is False` con el mensaje
`assert False is False`. El bbox viene de OpenCV y sus componentes son escalares de numpy: un
`np.float64` se propagaba hasta convertir la comparación en `numpy.bool_`, que **no es `True` ni
`False` por identidad**. Se arregló en el origen (`float()` en las tres componentes, no sólo en el
lado).

Lo destapó el `is True` del test. Con `assert x` en vez de `assert x is True` habría pasado
inadvertido, y la función habría devuelto un tipo distinto del que declara.

---

## Lo que me llevo

**Un fixture que no reproduce el bug es un resultado, no un fracaso.** Las capturas tenían que
confirmar la hipótesis y la desmintieron — y eso ahorró implementar un arreglo para una causa que
no era. El plan decía *"la representación exacta se elige midiendo sobre el fixture capturado, no
por decreto"*; lo que hacía falta medir no era el umbral, era la premisa.

**Y una media esconde un cambio localizado.** Las dos componentes viejas funcionan porque el texto
del panel cambia *en todas partes*. El recuadro de selección cambia en un borde, y promediarlo
sobre la región lo hace desaparecer. Cuando la señal es una posición, hay que **localizarla**.

## Lo que este cambio NO prueba

Que el p90 de 29 s se explique por esto. La correlación es real, pero el log en INFO no distingue
"la app no re-armó" de "re-armó y el disco no maduró" de "el usuario tardó más". Los dos intervalos
más largos de la corrida (155 s y 146 s) son pausas: los heartbeats muestran el monitor ciclando
sano en S9, sin excepciones.

Lo que sí está probado es que el gemelo **no puede** re-armar con la firma vieja, por construcción,
y que ahora sí. Cuánto de los 29 s era eso se mide en la próxima pasada, con `DANIBOD_LOG_DEBUG=1`.

---

**Archivos:** `app/core/detector.py` (`s9_selected_tile_pos`) · `app/core/monitor.py`
(`_s9_disc_signature`, `_s9_pos_movio`, `_is_new_s9_disc`, `_S9_POS_TOL_F`) ·
`app/tests/unit/test_monitor_s9_rearme.py` (nuevo) ·
`Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general/Ejemplo_15..18.png`.
