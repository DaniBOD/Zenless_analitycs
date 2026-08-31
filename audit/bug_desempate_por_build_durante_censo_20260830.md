# BUG — el desempate por build se realimenta a sí mismo durante el censo

**2026-08-30 23:08.** Reportado por Daniel en vivo: *"estoy parado en un disco equipado en Harumasa
y lo asigna a Antón"*. Es un **falso positivo**, no una abstención: escribe un dueño equivocado en
la DB.

Anotado, **sin arreglar** — el censo está corriendo y tocar el desempate en caliente cambiaría el
instrumento a mitad de la medición.

## La evidencia

```
23:08:06  DESEMPATE por equip:      Antón (0.88)  top=[Antón:0.88,    Harumasa:0.86, Lucía:0.70]
23:08:06  S17 persistido id=268 ... asignado=Antón          <- se escribe
23:08:11  DESEMPATE por equip_top2: Antón (0.88)  top=[Harumasa:0.88, Antón:0.86,    Lucía:0.69]
23:08:37  DESEMPATE por equip_top2: Antón (0.89)  top=[Harumasa:0.89, Antón:0.89,    Lucía:0.69]
23:08:45  DESEMPATE por equip:      Antón (0.86)  top=[Antón:0.86,    Harumasa:0.86, Lucía:0.69]
```

Dos cosas a la vez:

1. **El ranking visual se da vuelta entre frames.** Antón y Harumasa alternan el puesto 1 con
   diferencias de 0.00 a 0.03. Para el descriptor son el mismo avatar — igual que el par
   Antón/Manato, que se llevó 27 de las 43 abstenciones de la pasada anterior.
2. **El desempate promueve al top-2 por encima del top-1** (`equip_top2`) y elige Antón aunque
   Harumasa venga primero.

## Por qué el desempate elige mal

Mira la DB para ver "quién corre este set" y corrobora al candidato que lo tiene como set firma.
Estado real al momento del fallo:

| | discos de Tecno Pícido | discos en TODO el inventario |
|---|---|---|
| **Antón** | **4** (slots 3,4,5,6) | 4 |
| **Harumasa** | 1 (slot 4) | 1 |

Con eso la regla funciona como está escrita: Antón tiene una firma 4pc de Tecno Pícido, Harumasa
tiene una pieza suelta ⇒ corroboración exclusiva para Antón ⇒ se lo promueve.

**El problema es de dónde sale ese dato.** El censo está a mitad de camino: Harumasa tiene 1 disco
registrado porque todavía no se llegó a los otros, no porque no los tenga. La señal *"quién corre
este set"* se lee de la tabla que el censo está construyendo en este mismo momento.

Y peor: **si los 4 Tecno Pícido de Antón incluyen alguno mal asignado, cada error hace más probable
el siguiente.** El primero establece la firma 4pc que justifica al segundo. Es un lazo cerrado —
sospechoso, además, porque los 4 discos que Antón tiene en TODO el inventario son de ese mismo set.

## Lo que esto significa

El desempate por build **es sólido con la DB completa y no es una autoridad durante el censo**: lo
que lee es justamente lo que se está midiendo. La limitación documentada en el propio módulo
—*"no rescata ... sets filler compartidos por muchos PJs"*— es de la misma familia, pero más suave:
acá no es que el set no distinga, es que el dato todavía no existe.

## Candidatos a arreglo (a decidir con el censo cerrado)

- **Desactivar la promoción del top-2 mientras haya una pasada de censo abierta.** El más directo:
  con la DB a medio construir, el contexto no puede vetar a la vista. Se abstiene y el disco queda
  guardado sin dueño, que es recuperable; un dueño equivocado no.
- **Exigir que el candidato corroborado tenga cobertura suficiente del set** (p. ej. no promover si
  el otro candidato tiene 0 discos registrados *y* el censo está en curso: 0 puede significar "no
  lo tiene" o "todavía no lo vimos", y no se distinguen).
- **Atacar la causa visual**: Antón es un imán para Manato y para Harumasa. Sin separar esas clases,
  el desempate va a seguir siendo lo único que decide.

## Deuda de datos que deja

Hay que revisar los **4 discos de Tecno Pícido asignados a Antón** cuando cierre el censo, porque
al menos uno (id=268, slot 6, Recarga de Energía) es de Harumasa según el usuario. La revisión no
puede apoyarse en la propia DB.
