# Brief Claude Design — Prioridad de buildeo por PJ (Roster + modal de PJ)

> **Qué se pide:** que el usuario pueda **declarar y ver** la prioridad de buildeo de cada PJ
> (**alta / normal / baja**) dentro de la app. Es un dato que pone él, no algo que el sistema lee
> de la pantalla del juego.
>
> **Dónde vive:** la pantalla **Roster** (ya implementada, diseño v1) y el **modal de PJ** (ya
> implementado). No es una pantalla nueva: son marcas, un filtro y un editor sobre lo que existe.
>
> Sistema visual, tokens y componentes: `BRIEF_COMPLETO.md` (§1) y
> `mockups/design_v1_roster_y_pasivas/source/` (la plantilla de "pestaña de catálogo" y la celda
> 122×96). Implementación real: `app/ui/roster/{view,celda,filtros}.py`,
> `app/ui/pj_modal/modal.py`, `app/ui/tokens.py`.
>
> Datos reales del roster: [`ROSTER_datos_reales.md`](ROSTER_datos_reales.md) (hoy son **52 PJs**).

---

## 1. Para qué sirve (el porqué, para decidir bien el diseño)

El motor de discos sugiere **mover** un disco de un PJ a otro cuando al que lo recibe le mejora el
build y al que lo tiene no le empeora. Corrido sobre el inventario real (380 discos), **32 de los
108 movimientos iban a Piper**, un PJ que el usuario casi no usa, y le sacaban discos a PJs que sí
usa.
El sistema no tiene forma de saber a quién quiere mejorar el usuario: eso es la prioridad.

**Reglas ya decididas por el usuario (no son parte del diseño, pero el diseño las tiene que
comunicar):**

| | |
|---|---|
| niveles | **3: alta, normal, baja**. Todo PJ arranca en **normal**. |
| efecto | **bloquea**: nunca se sugiere sacarle un disco a un PJ para dárselo a otro de prioridad **más baja**. |
| misma prioridad | sigue la regla de siempre: se mueve sólo si el que lo tiene no pierde. |
| discos libres | van primero a los de prioridad alta. |
| naturaleza | es un **ajuste del usuario**: se puede cambiar cuando quiera, no se pierde con una recaptura. |

Uso esperado: al principio declara de una vez ~5–10 en alta y ~5–10 en baja; después lo toca de a
uno, cuando cambia de objetivo ("ahora quiero mejorar a Claret").

---

## 2. Lo que hay que diseñar

### 2.1 La marca en la celda del Roster (122×96)

La celda ya lleva cinco marcas, cada una con un significado y un color propios (README del diseño
v1, §2): esquina rayada **ámbar** = le faltan datos · `∞` cápsula **naranja** · nivel · seis
casilleros de discos · borde punteado **violeta** = atuendo.

- **Pintar sólo alta y baja.** Normal no se marca: es el caso de la mayoría (40+ de 52), y pintar
  el caso normal es ruido. Es el mismo criterio que ya usa el nivel (no se tiñe cuando es 60).
- **Alta** tiene que saltar a la vista en la grilla completa; **baja** tiene que leerse como
  "relegado", no como "error". La baja no es un problema del PJ: es una decisión.
- **Colores ocupados, no reusar:** ámbar `#F0AA3C` (faltan datos), naranja (∞), violeta `#B06FF0`
  (atuendo), y el violeta `--purple` de la familia de confirmaciones pasivas.
- La grilla se escala para entrar entera sin scroll: la marca tiene que sobrevivir a celdas más
  chicas que 122×96.

### 2.2 El filtro

La banda de filtros (104 px, tres filas de chips: elemento/rango, rol/facción, y la banda ámbar de
"estado de build") necesita poder filtrar por prioridad. Decidir si va como una fila más, como
chips dentro de una fila existente, o como otra cosa. Mismo contrato que los chips de hoy: el
conteo es sobre el roster completo, no sobre lo filtrado.

### 2.3 La leyenda

La leyenda de 32 px es **obligatoria** ("sin ella las marcas son adorno"): sumar alta y baja.

### 2.4 Editar de a MUCHOS — en el Roster (la declaración inicial)

Es el caso que más importa la primera vez: 52 PJs, marcar ~15 de una sentada. Abrir 15 modales es
inaceptable. Proponer un **modo de edición** dentro del Roster. Ideas a evaluar, no a copiar:

- un toggle "Editar prioridades" en el header (junto a "Declarar roster…") que convierte cada celda
  en un selector de 3 estados (click cicla normal → alta → baja, o una mini botonera en la celda);
- selección múltiple + "asignar alta / normal / baja" a la selección.

Tiene que ser obvio **en qué modo estás** (en modo edición el click NO abre el modal) y **cómo
salir**. Cada cambio se guarda al momento; no hay "Guardar" al final que se pueda olvidar.

### 2.5 Editar de a UNO — en el modal de PJ (1000×640)

Un selector de 3 estados en el modal del PJ, cerca del nombre o de la portada. Es el camino
natural cuando ya estás mirando a un PJ ("ahora quiero mejorar a este").

### 2.6 La confirmación

Al cambiar una prioridad **no sale un toast** (los toasts avisan cambios del juego, no ediciones
del usuario). El cambio se ve en la marca de la celda. Lo que sí hace falta comunicar, en algún
lugar discreto: que **las sugerencias de discos se recalculan** con la prioridad nueva.

---

## 3. Estados que tiene que cubrir el entregable

1. Roster **sin ninguna prioridad declarada** (los 52 en normal): ¿cómo se entera el usuario de
   que la función existe y de que conviene usarla?
2. Roster con prioridades — vista normal, con la leyenda. Datos de **ejemplo para el mockup**
   (sólo Claret en alta y Piper en baja son reales; el resto es relleno para ver la grilla con
   ~5 y ~6 marcas): alta = Claret Flint, Nekomata, Miyabi, Ellen, Yanagi; baja = Piper, Billy,
   Corin, Anby, Pulchra, Ben.
3. El mismo Roster en **modo edición** (§2.4), con una celda en hover y una recién cambiada.
4. Filtro por prioridad activo.
5. Modal de PJ con el selector, en los 3 valores.

---

## 4. Fuera de este brief

- **Mostrar las sugerencias** del motor ("a quién le sirve este disco", "mejoras disponibles para
  este PJ"): va en un brief propio, cuando el usuario haya revisado las sugerencias con la
  prioridad puesta. La marca de la ficha del disco ya tiene reservado ese lugar.
- Rangos objetivo por stat y pesos por PJ (también ajustes del usuario): después.
- Nada de esto cambia la regla de las recomendaciones en vivo (toasts EQUIPAR/MEJORAR/…).

## 5. Data model sugerido (para el render)

```js
{
  agente_id: 52, nombre: "Claret Flint",
  prioridad: "alta",            // "alta" | "normal" | "baja"; "normal" por defecto
  prioridad_actualizada: "2026-09-24T11:40"   // null si nunca se tocó
}
```
