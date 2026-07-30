# Tenencia del W-Engine: libre / de otro / equipada · RF-15 · 2026-07-30

**Pedido de Daniel:** *"detectar si el arma está Libre igual que los discos, porque puede swapear
el arma y si está libre no salta una confirmación; el botón de 'Reemplazar' o 'Equipar' pasa a
'Desequipar'."*

Es la misma distinción que en discos y por el mismo motivo operativo: **un arma libre se equipa
sin diálogo de confirmación**, la de otro PJ abre el diálogo (que cae en S23). Sin esta señal las
dos son indistinguibles, y río abajo eso es la diferencia entre "alta" y "mudanza" cuando esto
escriba la DB.

Sigue siendo **display-only**: no se escribe nada.

## Las dos señales

| Señal | Qué dice | Qué NO dice |
|---|---|---|
| Botón de acción (`read_s17_action_button`) | Si el PJ que mirás tiene algo puesto en ese slot | De quién es el arma |
| Badge de dueño (`read_weapon_owner_badge`) | Si el arma tiene dueño | Quién, salvo que la librería lo resuelva |

Cruzadas dan lo que ninguna da sola. Lo importante:

- **'Desequipar' identifica al dueño con certeza y sin librería.** Si el juego te ofrece
  desequiparla, la lleva puesta el PJ que estás mirando, y a ese lo sabemos por el latch de
  identidad (que sale del OCR de S18 y funciona para cualquier PJ). Es la única vía de dueño
  certero mientras `avatar_detbadge_v2` siga incompleta.
- **'Equipar'/'Reemplazar' + badge ausente ⇒ LIBRE.** Ese es el caso nuevo.
- **Presencia gana a libre**: 'Desequipar' se evalúa primero, así que un falso LIBRE del badge no
  puede contradecir al botón. Misma regla que ya rige en la ruta de discos.

El botón se midió sobre los 40 fixtures del panel de arma: **35 'reemplazar' + 5 'desequipar',
cero fallos de lectura**. Ya funcionaba en esta pantalla; lo que faltaba era usarlo.

## El badge, anclado al pill

`crop_detail_badge` (la ruta de discos) busca en `_DET_REGION`, una franja de coordenadas
normalizadas **fijas**. Es la misma trampa que ya había costado cara con la fila de estrellas: el
panel se corre verticalmente cuando el nombre del arma envuelve a dos líneas.

**Ejemplo_34 y Ejemplo_39 tienen avatar y la franja fija los da por libres.** El círculo entra
cortado por el borde del recuadro, así que lo que se mide no es el avatar.

El offset respecto del pill "Nivel N/M" es rígido — 28 muestras con avatar visible:

```
dx = cx - pill.x2 ∈ [163, 165]     dy = cy - pill.cy ∈ [-2, 0]     radio ∈ [23, 30]
```

Dos píxeles de rango en cada eje. El `crop` conserva el encuadre de `crop_detail_badge` (Hough +
`_DET_HOUGH_PAD`) a propósito: la librería se cosechó así, y un recorte distinto la volvería
inútil para nombrar. Lo único que cambia es **dónde se busca**.

## Por qué nitidez y no saturación

Acá estaba el hallazgo que no esperaba. Cuatro armas libres (Ejemplo_32/33/4/5) tienen un
**resplandor de color del arte del arma** justo detrás del hueco del badge. Por saturación pasan
por avatar con holgura:

| métrica | DUEÑO (28) | LIBRE (12) | gap |
|---|---|---|---|
| `\|Laplaciano\|` en el disco | 51.98 – 90.43 | 1.54 – 4.75 | **11×** ← se usa esta |
| `V_in - V_out` | 68.20 – 189.46 | −5.77 – 13.32 | 5× |
| `std_in` | 42.29 – 85.58 | 2.58 – 13.15 | 3.2× |
| área saturada | 103 – 7157 | 0 – **8002** | **se solapa** |

Brillo y saturación miden lo mismo que el resplandor. La nitidez no: **una cara tiene detalle, un
degradé no tiene ninguno.** Por eso el gap se abre a 11× en vez de solaparse. Umbral en 20.0 —
4.2× sobre el libre más alto, 2.6× bajo el dueño más bajo.

> Nota: el clasificador `s17_detail_is_face` **no sirve en esta ROI** (dio `True` en los 5 libres
> que probé). Está calibrado para el recorte ajustado a la cara que devuelve Hough, no para la
> ventana de búsqueda. No se usa acá.

## Resultado

| | franja fija | anclado |
|---|---|---|
| presencia correcta | — (confunde libre con fallo) | **40/40** |
| recortes para nombrar | 26/40 | **28/28 de los que tienen dueño** |

Y `present` sin `crop` es una salida legítima: "hay alguien, no sé quién". Antes eso era
indistinguible de "no hay dueño".

## Qué cambió

- `parser_weapon_s26.py`: `OwnerBadge`, `read_weapon_owner_badge`, `clasificar_tenencia`,
  `WeaponParsed.pill_bbox` y `.tenencia`.
- `monitor.py`: el handler de S26 cruza las dos señales; la tenencia entra en la firma del log
  (equipar el arma que estabas mirando cambia el estado sin cambiar el arma — ese evento hay que
  reportarlo).
- `toast.py` / `main.py` / `controller.py`: la tenencia va en la línea de rareza+nivel.
  `"incierto"` se muestra **vacío**: en una línea de tres campos, "tenencia incierta" ocupa el
  mismo lugar que un dato y se lee como si lo fuera.

## Tests

`test_parser_weapon_s26.py` (**379 passed**) y `test_monitor_weapon_s26.py` (**17 passed**).
Además del acierto, se fija el **margen**: un fixture nuevo que empiece a cerrar el gap de 11×
hace fallar el test antes de que un día cruce el umbral y aparezca como un dueño inventado.

## Pendiente

- **QA en vivo**, sobre todo el caso que los fixtures no cubren: abrir un arma libre, equiparla, y
  ver que la tenencia voltea de `libre` a `equipada` sin diálogo de por medio.
- **La ruta de discos sigue con la franja fija.** El mismo falso LIBRE que se arregló acá está
  latente allá — pero esa ruta **escribe la DB** y está muy calibrada, así que el cambio va
  aparte y con su propio QA.
