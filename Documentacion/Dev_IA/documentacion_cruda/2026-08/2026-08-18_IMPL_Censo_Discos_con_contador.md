# Censo de discos: el contador que el roster no tenía

> **2026-08-18** · `app/core/census_discs.py` (nuevo), `app/core/parser_disc_s17.py`

---

## 1. La asimetría con el censo del roster

El censo del roster se construyó sobre una ausencia. Verificado sobre las capturas: *"el menú de
personajes no tiene contador `N/M`"*. De ahí salió todo lo demás — la asimetría PENDIENTE ≠
HUÉRFANO, el cierre explícito por F8, y el corolario de que una corrida que nunca se cierra no
produce huérfanos jamás.

**Para discos no aplica.** El header del inventario dice `Pistas de disco [339/3000]`.

| | roster | discos |
|---|---|---|
| denominador | declaración del usuario (55) | **contador en pantalla (339)** |
| ¿sabe cuándo terminó? | no — lo declara el humano | **sí, hasta la brecha por gemelos** |
| autoridad del conteo | la declaración | **el header** |

Es la misma doctrina del `N/300` del desmontaje, donde el contador ya era *"la única autoridad del
conteo"* porque el viewport no ve todo y los tildes sólo sirven para aparear.

## 2. La brecha que el contador destapa

Y acá el contador hace algo más útil que dar un número: **expone un límite que sin él quedaba
invisible.**

El sistema deduplica discos por identidad `(set, slot, main, {substat + rolls})`, y sobre el
inventario real eso da **345 identidades para 367 discos** — 22 pares indistinguibles. Con 339 en
pantalla, una pasada perfecta registra ~317 y **nunca llega a 339**.

Dos salidas fáciles, las dos falsas:

| | por qué no |
|---|---|
| declarar completa al llegar al total | es una condición que no se cumple jamás |
| relajar el criterio para que cierre | miente sobre la cobertura |

La tercera es la del roster: **reportar la brecha y decir que no se puede cerrar sola.** Si el resto
son gemelos o discos sin visitar es otra pregunta, y el censo no la contesta a las apuradas.

```
faltan 22 de 339: o no se recorrieron, o son discos gemelos
(indistinguibles por identidad) que el censo cuenta una sola vez
```

Nombra la causa probable sin afirmarla. Con una pasada completa una brecha chica son casi siempre
gemelos — pero el censo no tiene cómo separarlos, así que no lo dice como si supiera.

## 3. Decisiones que los tests fijan

**`None` del OCR es "no pude leer", nunca "cero".** Sin ancla no hay cobertura que reportar. Y un
frame de transición que devuelve `None` **no borra** el ancla que ya había: perderla a mitad de
pasada dejaría al censo ciego.

**El contador puede cambiar durante la pasada** (farmeás o desmontás). Se re-ancla —quedarse con el
viejo daría una cobertura falsa— pero queda avisado: cambiarlo en silencio borraría la única pista
de que el inventario se movió. El aviso es por CAMBIO, no por lectura; el header se lee en cada
frame y avisar por lectura ahogaría el log.

**El excedente se reporta aparte.** Registrar más identidades que las que el header dice que existen
es señal de que algo no cierra (contador viejo, dos pasadas mezcladas). `faltan` nunca es negativo
y el sobrante tiene su propio campo, porque una cobertura de 105 % sin explicación es peor que un
número feo.

**Libre ≠ sin resolver.** `libre` es una afirmación (se leyó la esquina del tile y no hay avatar),
no la ausencia de dueño. Los vistos que no resolvieron ninguna de las dos cosas cuentan para la
cobertura y **no** para las otras cuentas: mezclarlos con los libres inflaría un número que después
se usa para validar la pasada.

## 4. El lector del contador

`parse_s9_header_counter`, mismo molde que el del desmontaje: ROI del header, OCR, regex con el
`/3000` como **ancla** — sin él, la batería del header superior (`237/240`) o cualquier par de
números se leería como un inventario.

Una diferencia con el desmontaje que vale anotar: allá PaddleOCR lee el `300` como `3o0` de forma
consistente y hubo que normalizar confusiones de dígitos. **Acá no hace falta: 14/14 fixtures leen
limpio.** No se agregó el `translate` preventivo — RNF-02 también aplica a los arreglos: no se
inventan para fallas que no se observaron. Si aparece un `3o00`, el lugar está señalado.

## 5. Lo que falta para salir a capturar

El módulo es puro y el lector está calibrado. Queda el cableado: que el handler de S9 lea el
contador con su propia cadencia (no en cada frame — RNF-06), alimente `DiscSighting` con la
identidad que ya calcula `_disc_identity`, y exponga apertura/cierre de la corrida.

---

## 6. El cableado en el monitor

**La corrida se abre sola.** Hay un disparador claro —estás en el inventario— y, a diferencia del
roster, no hace falta que el usuario declare nada para que el censo sepa cuánto le falta.

**Y no se reabre después de cerrada.** Volver a la pantalla tras cerrar no debe empezar a contar
sobre lo ya reportado sin que se note: es exactamente el problema que tuvo el censo del roster
(QA 2026-08-17), donde una segunda corrida declaraba huérfanos a los PJs de la primera.

**El contador se lee con cadencia propia (5 s), no por frame.** Es un OCR dentro de un handler
continuo — leerlo en cada frame es lo que RNF-06 prohíbe, y el denominador cambia poquísimo.
Releerlo alguna vez sí hace falta: farmear o desmontar durante la pasada lo mueve.

**La identidad es la misma que la del dedup de emisión** (`_disc_identity`). Dos definiciones de
"mismo disco" en el mismo flujo sería una de más: el censo contaría distinto que la persistencia y
ninguna de las dos cuentas quedaría verificable contra la otra. Hay un test que lo fija.

**F8 cierra el del inventario primero** si está abierto, porque es el que tiene contador y produce
un número verificable; si además hubiera una corrida de roster abierta, se cierran las dos.

El cierre reporta cobertura, y cuando queda corta lo dice:

```
[censo-discos] pasada cerrada — 317/339 registrados · 245 con dueño · 72 libres · 0 sin resolver
[censo-discos] faltan 22 de 339: o no se recorrieron, o son discos gemelos …
```
