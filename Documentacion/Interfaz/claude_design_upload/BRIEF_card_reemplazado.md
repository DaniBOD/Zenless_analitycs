# Brief Claude Design — Card/Toast "REEMPLAZADO" (disc swap detectado)

> 5ª variante del toast flotante de DaniBOD ZZZ Analytics. Se suma a las 4 existentes
> (EQUIPAR, MEJORAR, RESERVA, DESCARTAR) y a la card LATEGAME. **Reusar el mismo sistema**:
> componentes `BlockBox`, `DiscThumb`, `Rarity`, `Icon`, `ZButton`, `Countdown`, `UrgencyBar`
> y los tokens de `tokens.css`. Mismo frame **380×116**, esquina inferior derecha, always-on-top.
> Código base de referencia: `mockups/Codigos-claude-desing/toasts.jsx`.

## Propósito

Cuando el sistema detecta (vía OCR de la pantalla de confirmación de sustitución de disco) que un
**disco se movió de un PJ a otro**, emite esta card. Es una **CONFIRMACIÓN / SINCRONIZACIÓN**, NO
una recomendación con call-to-action. Comunica: *"detecté el reemplazo y actualicé la DB"*.

Ejemplo real del juego que la dispara: *"Yixuan equipa actualmente Balada de la rama y la espada (2).
¿Deseas sustituirlo?"* → al confirmar, ese disco pasa de **Yixuan** a, p.ej., **Nangong Yu**.

## Diferenciación vs las 4 cards de recomendación

| | 4 cards recomendación | **Card REEMPLAZADO** |
|---|---|---|
| Naturaleza | call-to-action (equipá/mejorá/…) | confirmación pasiva (ya pasó) |
| Color acento | positive / info / yellow / warning | **`--purple` (#9D4EDD)** (libre, sin usar) |
| Score grande | sí | **no** (sobrecarga; no aplica) |
| Barra de urgencia | sí (pulsa) | **no** → línea de estado estática "SINCRONIZADO" |
| Countdown top-right | cuenta regresiva de acción | micro-badge **"✓ SINCRONIZADO"** + auto-dismiss ~3s |

## Layout (380×116, mismo `BlockBox` carbon + glassTop, borde/glow violeta)

**Header** (igual estilo que las otras): chip con esquina chaflanada + ícono de **swap/intercambio**
(dos flechas ⇄) en violeta, label **"REEMPLAZADO"** en caps violeta, divisor, `#id` del evento.
Top-right: en vez del Countdown de acción, un micro-badge **"✓ SINCRONIZADO"** (verde `--positive`
tenue) o "DB ✓".

**Body — el movimiento `PJ_origen → disco → PJ_destino`:**
- **Izquierda:** avatar circular del **PJ que deja** el disco, **atenuado** (opacity ~0.55, borde
  `--border-mid`). Debajo, micro-label **"DEJA"** (caps, `--text-muted`).
- **Centro:** `DiscThumb` con el logo del set (tier S badge), y una **flecha →** violeta que cruza
  del origen al destino pasando por el disco. Debajo del thumb: **`<Set> · Slot N`** (sin substats,
  sin score — mínimo, para no recargar). El set en `--text-primary`, el "Slot N" en `--text-muted`.
- **Derecha:** avatar circular del **PJ que equipa**, **resaltado** (borde violeta + glow
  `--purple`). Debajo, micro-label **"EQUIPA"** (caps, violeta).

**Footer:** en lugar de `UrgencyBar` pulsante, una **barra fina estática violeta** + línea de estado:
izquierda **"EQUIPAMIENTO SINCRONIZADO"** (caps, `--text-muted`), derecha **`slot N · S`** o
**"inventory_discs ✓"** (mono, `--text-muted`).

## Estados

- **idle:** opacity 0.96, auto-dismiss ~3 s (más corto que las de acción; es informativa).
- **hover:** pausa el auto-dismiss, opacity 1, prompt inferior `CLICK ABRIR PANEL · HOVER CONGELADO`.
- **fade-out:** opacity 0.35, salida 200 ms.
- (No hace falta el estado "expanding/score" de las cards de recomendación.)

## Data model sugerido (para el render)

```js
{
  id: "00731",
  disc: { set: "Monarca del Pináculo", slot: 2, tier: "S", setLogo, accent: "#9D4EDD" },
  from: { name: "Yixuan",     ico, mind: 1 },   // PJ que pierde el disco (atenuado)
  to:   { name: "Nangong Yu", ico, mind: 0 },   // PJ que lo equipa (resaltado)
  synced: true                                  // DB actualizada
}
```

## Notas de contenido (mínimo, anti-sobrecarga)

- Del disco mostrar **solo set + slot** (+ rareza en el thumb). NADA de substats/main/score.
- Los dos avatares con su **nombre** (truncado si hace falta) y opcional `M<mindscape>` chico.
- El acento violeta debe estar en: borde del frame, ícono swap, flecha, ring del PJ destino, barra
  inferior. El PJ origen y los textos secundarios quedan en grises (`--text-muted`/`--border-mid`).

## Entregable

1 card en los 3 estados (idle / hover / fade), 380×116, sobre fondo de escritorio para contexto
(como los mockups `Toast-en-escritorio-contexto-real*.png`). Reusar tokens y componentes existentes.
