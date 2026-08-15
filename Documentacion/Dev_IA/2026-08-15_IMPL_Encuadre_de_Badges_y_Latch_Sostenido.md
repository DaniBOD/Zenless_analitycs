# El encuadre de los badges y el latch sostenido — 2026-08-15

> **Qué pasó:** salimos a subir el naming del dueño de un W-Engine cosechando más referencias.
> Resultó que **el problema nunca fue la cantidad de refs**: era que nadie normalizaba el ENCUADRE
> del recorte. Y en el camino, el QA en vivo destapó un agujero de atribución que sobrevivía a tres
> capas de guardas.
>
> Commits: `b9af74d` (lectura S30) · `c437d75` (cosecha) · este doc cubre además el guard del latch.

---

## 1 · El diagnóstico que era falso

Veníamos de dos pasadas de QA con el mismo diagnóstico: *"faltan referencias"*. Se cosecharon refs
para tres PJs y mejoró poco. Lo que lo desarmó fue el banco de verdad de tierra
(`app/tests/unit/test_s30_dueno_verdad_de_tierra.py`, 10 armas con dueño confirmado a ojo):

- **La cantidad de refs no explicaba nada.** Gatillo con **3** refs caía en 0.255; Vivian con **2**
  en 0.080.
- Las distancias se partían en **dos regímenes** — bajo 0.09 los seguros, entre 0.20 y 0.31 los
  dudosos — y **nada en el medio**. Un continuo de "calidad" no se ve así; dos poblaciones sí.

## 2 · La causa: Hough decidía el zoom

El badge del dueño es un **elemento de UI de tamaño fijo**. El código lo localizaba con Hough y
usaba *el radio detectado* para recortar. Ese radio aterrizaba en dos sitios:

| qué encontró Hough | radio | qué queda en el recorte |
|---|---|---|
| el círculo de la CARA | ~21 px | la cara, ajustada |
| el borde EXTERIOR del badge | 25.8 px *(idéntico en 4 de 7)* | la cara **+ un anillo de fondo** |

Con el anillo, la cara ocupa menos cuadro; tras el resize del descriptor, es otra composición. **Se
ve a simple vista volcando los crops lado a lado** — y ese fue el momento en que dejó de ser teoría.

> **Lección de método:** habíamos medido histogramas, distancias y matrices antes de mirar las
> imágenes. Mirarlas fue lo más barato y lo más concluyente. Cuando el objeto de estudio es visual,
> verlo va antes que medirlo.

**Detectar lo que es constante solo mete varianza.** Hough tiene que LOCALIZAR (el centro, que
resuelve bien); el radio sale de una constante.

### Eran TRES caminos, no dos

`crop_detail_badge` (S17 + S26) era el que teníamos identificado. Pero **la cosecha de S26 no pasa
por ahí**: usa `read_weapon_owner_badge`, con su propio Hough — y es la que había cosechado a Jane,
Nangong Yu y Zhao. Ahí los lados se partían en 48-52 y **60-62**, con cuatro de los cinco crops de
62 px entre los peores matches de la tanda.

| camino | constante | antes | después |
|---|---|---|---|
| `read_weapon_owner_badge_s30` (lectura S30) | `_S30_OWNER_R_F` = 21/2559 | 4/7 nombrados | **6/7** |
| `crop_detail_badge` (S17+S26) | `_DET_CROP_R_F` = 25/2559 | 67/95 bajo 0.15 | **74/95** |
| `read_weapon_owner_badge` (cosecha S26) | `_DET_CROP_R_F` | 11/30 · 22 nombrados | **17/30 · 26** |

**Cero cambios de identificación en los 125 badges.** Era el número que hacía falta antes de tocar
nada: el dueño alimenta `sync_equip`, que escribe la DB.

### Por qué 25 y 21 conviven

**Lo que tiene que coincidir entre superficies NO es el radio en píxeles sino la FRACCIÓN de cuadro
que ocupa la cara.** S17 y S26 dibujan el badge en el panel central, al mismo tamaño; S30 lo dibuja
en un panel más angosto y sale más chico. Misma fracción, distinto radio.

### Lo que NO es

**No es volver al radio fijo que falló en 2026-06-17.** Aquel era ~96 px para un avatar de ~55:
ahogaba la cara en fondo a rayas y el descriptor se agrupaba por página. La lección de entonces fue
*no recortar ancho*, no *no usar una constante*. Queda escrito en el código para que nadie lo lea
como una vuelta atrás.

### Lo que quedó abierto

- **Zhao** mejora en la dirección CONTRARIA (0.050 a r=27): sus refs entraron por el camino más
  roto y quedaron anchas. Normalizar evita que entren más; **no repara las que están**.
- De 31 clases con ≥2 refs, **17 tienen encuadres mezclados**. Es un **piso**: el proxy detecta
  inconsistencia interna, así que una clase con todas sus refs igual de mal encuadradas sale
  "coherente" — justo el caso de Zhao.
- **Grace** (`Ejemplo_7`) sigue en `xfail`: afirma LIBRE un arma que tiene dueño. Es DETECCIÓN, no
  identificación, y está acotado — dos armas realmente libres se reportan bien.

---

## 3 · El QA en vivo, y el agujero que destapó

Readonly, cosecha apagada. **28 discos en 5 PJs: cero atribuciones erróneas**, confianzas 0.82-1.00.
DB con el mismo sha256 antes y después.

El mejor dato fue uno que parecía un error: en medio de los discos de Nekomata, uno se votó
**Jane** — y era correcto, porque su slot 5 está vacío y el primero de la grilla es de Jane.

Pero Daniel notó a ojo algo que el resultado no mostraba: *"pasando de la pantalla de equipamiento
de un PJ a otro, a veces no lo capta"*.

### Qué significa exactamente "sostenido"

`_detail_source == "sostenido"` se asigna en **un solo lugar** del código, y solo cuando:

1. la barra de avatares está **visible** (`cur_x is not None`),
2. **no** estamos en la ranura donde se confirmó la identidad, y
3. el matcher **no pudo** reconocer al PJ.

O sea: **la selección se movió y no sabemos hacia quién.** `_last_agent_name` es el del PJ anterior.

Que el caso de auto-hide (barra oculta) salga *antes*, sin tocar la etiqueta, es lo que hace usable
la señal: no mezcla *"no veo nada"* con *"veo otra cosa"*.

### Por qué tres guardas no lo tapaban

El ancla de flujo ("el 1er disco de un slot nuevo es el equipado por el latch") ya tenía **veto por
botón**, **warm-up** y **cross-check contra el badge**. Pero el cross-check solo ataja cuando el
badge dice **OTRO** PJ. Si el badge no dice **nada**, asignaba al latch con conf 1.0 y cosechaba
bajo ese nombre.

> **Y los dos fallos están CORRELACIONADOS.** El latch se sostiene porque el matcher de FILA no
> reconoce a ese PJ; el badge calla porque el de GRILLA/DETALLE tampoco. Misma causa —refs flacas—,
> así que **justo cuando el latch queda viejo, la guarda que debería atraparlo está muda**.

Eso es lo que explica que sobreviviera a tres capas: no eran independientes.

### El arreglo

Latch sostenido **+** badge sin voto ⇒ se desactiva el ANCLA y se cae al camino por evidencia
(voto, sim-a-latch, LIBRE, desempate por contexto). Ese camino puede resolverlo igual de bien o
declararlo incierto; lo que ya no puede es afirmar certeza sin confirmación.

**Sostenido no es veneno, es falta de confirmación.** Si el badge vota y coincide, el ancla sigue
valiendo — hay un test dedicado a eso, para que nadie "arregle" esto apagando el ancla entera y
pierda atribuciones correctas.

---

## 4 · Lecciones transferibles

1. **Contar no es medir.** Primero fue "contar refs no es medir cobertura" (los clones); ahora
   "contar refs no explica el naming" (el encuadre). Dos veces la misma trampa con distinta cara.
2. **Detectar lo que es constante mete varianza.** Si un elemento de UI tiene tamaño fijo, su
   tamaño es un dato del diseño, no una medición.
3. **Mirar antes de medir**, cuando el objeto es visual. Los crops lado a lado resolvieron en un
   minuto lo que tres tandas de histogramas habían dejado ambiguo.
4. **El grupo de control es lo que convierte una correlación en causa.** Dialyn se arregló sin
   recibir una sola ref nueva; sin ese caso, "cosechamos y mejoró" no distinguía las dos hipótesis.
5. **Guardas que comparten causa raíz no son capas independientes.** Tres protecciones y ninguna
   servía, porque las tres dependían del mismo matcher.
6. **Ignorancia ≠ desacuerdo.** El patrón se repitió tres veces en esta tanda: un tope de nivel
   ilegible no veta, un matcher sin opinión deja cosechar, una barra oculta sostiene. Lo que veta
   es siempre evidencia POSITIVA en contra.
