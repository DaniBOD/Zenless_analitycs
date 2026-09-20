# Fase 2C: el detector lanzaba Tesseract en cada vuelta

**2026-09-20 · PERF** · sigue al
[QA de la medición](2026-09-20_QA_El_menos_18_por_ciento_no_existia.md), que dejó la regla con la
que se midió esto.

## 1. La premisa de la fase era falsa

La Fase 2C existía para atacar **el OCR del panel**, que el PERF de la Fase 2 señalaba como "el
tramo más grande que queda" (p50 1608 ms). Primera medición, sobre el corpus de S9:

```
parse_disc_s9 completo       p50 1006 ms   (el OCR es el 100 % de eso)
  el panel (1 llamada/disco)     889 ms    83 % del OCR
```

Pero la espera real (click→log) es **3,5 s**. O sea que el parseo entero —panel incluido— es
**menos de un tercio** del problema. Optimizar ahí habría pulido el 28 % creyendo que era el 100 %.

Daniel: *"el tema de la latencia es la medición"*. La premisa de la fase venía del mismo documento
cuyo titular ya habíamos invalidado.

## 2. Tres hipótesis mías, las tres refutadas por su propio control

| hipótesis | cómo se cayó |
|---|---|
| "el `detector` se encareció de 190 a 585 ms" | controlando por PANTALLA: en S9 **siempre** costó ~500-585 ms; los 190 eran otras pantallas |
| "el OCR cuesta por píxel (826 ms/Mpx)" | escalar la imagen a **un quinto** no ahorró nada: 670 ms contra 754 |
| "el costo es fijo por llamada" | tampoco: era el **contenido**. Paddle cobra por línea de texto detectada |

La segunda dejó además un dato para no repetir el intento: escalar a 0,85 **corrompió un dato**
(un substat pasó de `+1` a `+0` rolls). Achicar la imagen no es gratis aunque fuera rápido.

Y una cuarta, esta vez sobre mi propia medición: vi `_read_inventory_header` con "p50 282 ms y 2
llamadas por `classify`" y casi concluyo que el caché no servía. Separando las dos llamadas: la
primera 323 ms, **la segunda 0,0 ms**. El caché funcionaba perfecto y mi p50 caía justo en el
borde entre las dos poblaciones — la misma trampa de paridad que había documentado esa mañana.

## 3. Lo que sí era

```
classify → _clasificar → _verify → _verify_s30 → _read_inventory_header → tesseract.exe
```

S9 (inventario de discos) y S30 (inventario de amplificadores) **comparten template**. Para saber
en cuál estás, el detector **leía el título con Tesseract, lanzando un proceso externo, en cada
vuelta del loop**:

| | |
|---|---|
| `classify` en el inventario | **518 ms** |
| de eso, leer el header | **323 ms — el 62 %** |
| el resto (matcheo de plantillas) | 198 ms |

Y en la espera de Daniel entran **dos vueltas** (el avistaje y la pasada de confirmación), así que
se pagaba **dos veces por disco**.

Esto ya se había intentado atacar el 2026-09-16 con una caché del header "por contenido", revertida
al día siguiente por acertar **0 de 72** en vivo. Era la idea correcta con la llave equivocada: los
frames nunca son idénticos píxel a píxel.

## 4. El arreglo: mirar la pestaña, no leer el título

El pill lima de la pestaña activa dice lo mismo en HSV puro. **Medido sobre los dos corpus** (19
capturas de S9 + 18 de S30), centroide horizontal del lima en la franja `y 0.11-0.19`:

| | rango | dispersión |
|---|---|---|
| discos | 0.8065 – 0.8074 | 0.0009 |
| armas | 0.7571 – 0.7572 | 0.0001 |

**Separación 0.0493: unas 50 veces la dispersión interna.** Lo que discrimina es el **margen**, no
un umbral absoluto — la forma que este proyecto ya vio fallar tres veces (Prácticas C1). Por eso se
decide por centro más cercano con tolerancia y **se abstiene** si no cae claro; ahí cae al OCR, que
sigue siendo la autoridad. No reemplaza la evidencia: antepone una más barata.

| | antes | ahora |
|---|---|---|
| `classify` en S9 | 518 ms | **164 ms** |
| `classify` en S30 | — | 161 ms |
| llamadas a Tesseract | 1 por vuelta | **0** |
| clasificación | 19/19 S9 · 18/18 S30 | **idéntica** |

Esperado en la espera: **~700 ms** (dos vueltas), más un loop más rápido en todo el inventario.

### La progresión completa de esta misma optimización

| | lecturas del header por `classify` |
|---|---|
| antes de agosto | **2** (los dos verifies pedían el mismo recorte) |
| caché por clasificación (2026-08-19) | **1** |
| discriminador de pestaña (hoy) | **0** |

## 5. Un contrato que cambió, dicho en el nombre del test

`_verify_s30` **fallaba cerrado sin OCR**: sin título legible, el frame volvía a S9. Hoy el pill es
evidencia por sí solo, así que sin Tesseract S30 igual se verifica. El test viejo se renombró a
`test_verify_s30_falla_cerrado_sin_NINGUNA_evidencia` y se le agregó su contracara,
`test_s30_se_verifica_SIN_tesseract_gracias_al_pill`. Lo que sigue fallando cerrado es no tener
ninguna de las dos.

Los cuatro tests del caché del header quedaron en rojo por una razón que **no era un defecto**:
cuentan lecturas durante un `classify` y ahora no hay ninguna. Corren con el **pill ciego**, que es
el camino que realmente protegen, y se sumó el test de lo nuevo: en el camino normal el header no
se lee **ni una vez**.

## 6. Sabotajes

5 de 5 en rojo, hash del diff idéntico antes y después: invertir los centros, sacar la tolerancia,
correr la franja, y que cada uno de los dos verifies ignore el pill.

**Uno quedó VERDE en la primera tanda:** sacar la guarda del margen no rompía nada. El test de
abstención usaba un frame negro, que se iba antes por "no hay lima" y **nunca llegaba a la
tolerancia**. Se agregó un pill **sintético en una posición ajena** (x 0.65 y 0.90): ahí la guarda
sí se ejercita, y el sabotaje pasó a rojo. Una guarda que ningún test puede tumbar no está
verificada, sólo escrita — es la segunda vez en dos días que aparece esta misma forma.

## 7. Lo que falta

- **Verificarlo en vivo.** Los 164 ms son de corpus, no de pasada real. La medición tiene que ser
  con **n ≥ 100 y su intervalo** (regla C1.b): ~10 min de pasada por condición.
- La espera sigue teniendo **~1 s de parseo** y la cadencia del loop. Con el detector a 164 ms, el
  siguiente candidato es el período del loop (p50 1093 ms en el censo), del que el `classify` era
  más de la mitad.
- Los otros dos call-sites de OCR del panel (11 % y 6 % del total) siguen sin tocar.
