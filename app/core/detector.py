"""
Hito 2.4.4 — Detector de estado de pantalla (S1-S18) · RF-04 §4.
Tres capas de detección:
  Capa 1: template matching (cv2.matchTemplate TM_CCOEFF_NORMED)
  Capa 2: verificación secundaria por estado (elementos UI únicos)
  Capa 3: clasificador HSV fallback (paleta de color)
Slot detection multi-método:
  Método A: OCR del título "Set Name (N)"
  Método B: Aro brillante HSV (glow verde/amarillo del slot seleccionado)
State machine para validación de transiciones anti-FP.
"""
from __future__ import annotations

import contextvars
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.core.metrics import measure_latency

# =========================================================================
# Constantes
# =========================================================================

# Regex para extraer numero de slot del titulo "Set Name (N)"
_SLOT_RE = re.compile(r"\((\d)\)")
_S17_SLOT_RE = _SLOT_RE

# ROIs normalizadas para slot detection (S17 panel central, S9 panel derecho)
_S17_TITLE_ROI = (0.310, 0.115, 0.300, 0.070)
_S9_TITLE_ROI  = (0.680, 0.220, 0.200, 0.085)

TEMPLATES_DIR = Path(__file__).parent.parent / "resources" / "templates"

# Threshold global por defecto
MATCH_THRESHOLD = 0.85

# --- Pase grueso del matcheo de templates (Dev_IA 2026-08-19) --------------------------------
# `cv2.matchTemplate` hace el trabajo pesado del lado de la IMAGEN (integrales + correlación por
# bloques con DFT sobre el frame entero) y lo RECOMPUTA en cada llamada. Medido: ~106 ms por
# llamada sobre un frame de 3,7 Mpx **sin importar el tamaño del template** — uno de 8×8 cuesta lo
# mismo que uno de 1022×431. Con 31 templates eran ~3,1 s por frame, el 83 % del ciclo del monitor.
#
# El arreglo NO es bajar la resolución del match (eso obligaría a recalibrar los 26 umbrales de
# THRESHOLD_BY_STATE): el pase grueso solo LOCALIZA, y el score que decide se sigue calculando a
# RESOLUCIÓN COMPLETA sobre el píxel original, dentro de un ROI chico.
_COARSE_SCALE = 0.25          # escala del pase que localiza
_COARSE_PAD = 24              # px (full-res) de margen del ROI de confirmación
_COARSE_MARGIN = 0.15         # cuánto por debajo de su umbral puede estar un template en el pase
                              #   grueso y todavía merecer confirmación. El peor positivo del
                              #   corpus quedó a 0.029 de su umbral ⇒ ~5× de holgura.
_COARSE_MIN_PIXELS = 1_000_000  # por debajo de esto el frame va directo: no hay nada que ahorrar
_COARSE_MIN_TMPL = 8          # px; un template más chico que esto al 1/4 no discrimina ⇒ directo
_COARSE_PEAKS = 3             # picos del mapa grueso que se confirman por template. Con UNO solo
                              #   alcanza el 99 % de las veces (la distancia entre el argmax grueso
                              #   y el real es p50 = 1 px), pero llegó a 167 px en un caso: ahí el
                              #   ROI mira el lugar equivocado y el score sale bajo. Tres picos
                              #   cierran ese agujero por ~4 ms cada uno.
_COARSE_DIAG_TOP = 3          # templates que se confirman SIEMPRE, aunque no lleguen al shortlist,
                              #   para que el diagnóstico de S12 sea fiel. No es cosmético: esa
                              #   confianza decide en `monitor` si un frame resetea la identidad
                              #   latcheada (umbral 0.50). Con top-1 hubo 1 cruce de ese umbral en
                              #   102 frames; con top-3, ninguno.

# Thresholds dinámicos por estado (más permisivos para pantallas informativas,
# más estrictos para captura crítica)
THRESHOLD_BY_STATE: dict[str, float] = {
    "S3":  0.85,   # Modal detalle drop — crítico, evitar FPs
    "S6":  0.85,   # Vista individual del disco — crítico
    "S7":  0.85,   # Vista individual del disco — crítico. El template `s7_detalle_full_iconos`
                   #   (cluster papelera/candado/R/T) es chrome de UI ⇒ invariante al nivel, al
                   #   set y al wallpaper: medido 0.997–1.000 en los 3 fixtures de la vista vs
                   #   ≤0.74 en S17/S9/S10/S5/S22/S2 y ≤0.45 en los 37 negativos de QA.
                   #   Los otros dos templates de esta pantalla matchean por accidente y NO se
                   #   puede depender de ellos: `s7_tienda_detalle_full` incluye el texto
                   #   "Nivel 15/MAX" (solo matchea discos maxeados) y `s6_tienda_detalle_panel`
                   #   es una banda oscura que matchea por el FONDO de Ejemplo_6, no por UI.
    "S10": 0.80,   # Modal upgrade — template = barra botones "Añadir/Mejorar" (estable entre
                   #   niveles, única de S10). Los S10 reales matchean ≥0.85, los NON-S10 ≤0.50 →
                   #   0.80 da margen para la deriva de captura viva (mss 2560×1440) sin FP.
    "S2":  0.80,   # Resultado desafío — anti-FP. El template s2 es una banda superior dominada
                   #   por fondo oscuro → sobre-matchea bandas oscuras (S13 ~0.90, ciertas guías
                   #   ~0.72). Umbral 0.80 las excluye. El evento doble-recompensa (que baja el
                   #   template normal a 0.77 por el banner "×2") se cubre con un TEMPLATE PROPIO
                   #   (s2_resultado_desafio_evento.png). El eclipse de S13 (0.90≥0.80) lo maneja
                   #   el fallback de verificación en classify. Ver QA farmeo 2026-07-07.
    "S5":  0.80,   # Resultado afinación — ventana breve
    "S8":  0.80,   # Vista agente — informativo
    "S11": 0.80,   # Desmontaje — anti-FP
    "S24": 0.85,   # "Obtenido" post-desmontaje — título genérico, exige _verify_s24
    "S25": 0.85,   # Diálogo de confirmación del desmontaje ("...pistas de grado S. ¿Seguro que
                   #   quieres desmontarlas?"). COMPARTE el template de S23 (la fila genérica
                   #   "Cancelar/Confirmar", que matchea 0.996-0.998) y se distingue por el texto.
                   #   No commitea nada: solo congela el conteo declarado antes de que el diálogo
                   #   tape el header y el contador N/300 se vuelva ilegible (QA 2026-07-25).
    "S17": 0.75,   # Detalle disco PJ — informativo, más permisivo
    "S26": 0.75,   # Detalle de W-Engine equipado. COMPARTE el template de S17: la pantalla del
                   #   arma y la del disco son la misma salvo por el contenido del panel, y
                   #   matchean las dos a 1.000. Mismo umbral por eso mismo — lo que separa es
                   #   `_verify_s26` (texto "avanzados"/"amplificador").
    "S27": 0.80,   # Canal de sintonización (banner) — ANTELACIÓN A CAPTURA. Template = franja de
                   #   botones "1 sintonización / 10 sintonizaciones", que es cromo FIJO. El arte
                   #   central del banner cambia ENTERO cada patch (mapa de desvío sobre los 6
                   #   banners de 3.1): anclarse ahí sería morir en 3.2. Medido contra 7 grillas +
                   #   splash + animación + 30 negativos: positivos ≥0.958, negativos ≤0.527 ⇒
                   #   0.80 deja ~0.27 de margen bajo el peor positivo y ~0.27 sobre el peor FP.
    "S28": 0.85,   # Resultados de sintonización (grilla 5×2). Template = el título, que da el
                   #   hueco más ancho de todos los recortes probados: positivos ≥0.992 vs
                   #   negativos ≤0.464. Umbral alto igual, porque de esta pantalla salen las
                   #   recompensas y un FP mentiría sobre lo que salió; va con `_verify_s28`.
    "S18": 0.75,   # Perfil agente (Atributos base) — informativo
    "S19": 0.75,   # Perfil agente (Habilidades) — informativo, sin extracción
    "S9":  0.80,   # Inventario discos — informativo
    "S13": 0.70,   # Selección set farmeo — transición
    "S14": 0.70,   # Selección equipo — transición
    "S15": 0.70,   # Menú personajes — transición
    "S16": 0.80,   # Detalle set disco — anti-FP
    "S1":  0.70,   # Patrulla — apenas para saber que no es capturable
    "S4":  0.70,   # Tienda selector — transición
    "S20": 0.78,   # Popup "Materiales recuperados" (vuelto post-mejora) — título centrado único.
                   #   Target matchea 1.00, los NON-S20 (S10/S17/pre-max) ≤0.63 → 0.78 con margen.
                   #   NON_CAPTURE + acción inocua (refresca el pendiente) → un FP no hace daño.
    "S21": 0.85,   # Modal "Selecciona el número de usos" (baterías) — título largo y único sobre
                   #   modal opaco. Arma la previa del farmeo (nº de corridas) → convención ≥0.85.
    "S22": 0.85,   # Modal "Obtenido" (drops del farmeo por baterías) — captura crítica: con
                   #   auto-combate NO hay S2 ni S3 después, es la ÚNICA ventana donde existen
                   #   estos drops. "Obtenido" es un título genérico (correo/login/pase) → el
                   #   umbral alto va acompañado de _verify_s22 (franjas de rareza en la grilla).
    "S23": 0.85,   # Diálogo de sustitución de disco entre PJs ("{PJ} equipa actualmente {set}
                   #   ({slot}). ¿Deseas sustituirlo?") — arma un WRITE a DB (mover disco), así
                   #   que umbral alto. Template = fila "Cancelar/Confirmar" (genérica de ZZZ) →
                   #   acompañado de _verify_s23 (OCR del texto "sustituirlo").
    "S29": 0.85,   # Diálogo de sustitución de W-ENGINE entre PJs. MISMA frase que S23 salvo por el
                   #   sufijo de slot: el disco dice "... {set} (4). ¿Deseas sustituirlo?" y el arma
                   #   "... {arma}. ¿Deseas sustituirlo?" — un arma no tiene slot. Mismo template y
                   #   mismo umbral que S23 por eso; lo que separa es `_verify_s29`.
    "S30": 0.80,   # Inventario general de AMPLIFICADORES (W-Engines). COMPARTE el template de S9:
                   #   es la misma grilla con el mismo panel de detalle a la derecha y matchea
                   #   `s9_inventario_general.png` a 0.855-0.864. Mismo umbral que S9 por eso; lo
                   #   que separa es el título, vía `_verify_s30` / `_verify_s9`.
    "S12": 0.0,    # Sin coincidencia — no aplica
}

# Máquina de estados: transiciones válidas desde cada estado previo.
# Si un estado detectado no está en las transiciones válidas → FP → S12.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    None:  {"S1", "S4", "S12", "S13", "S14", "S15", "S27"},
    "S1":  {"S2", "S12", "S13", "S14", "S15", "S4", "S27"},
    "S2":  {"S3", "S12", "S11"},
    "S3":  {"S12", "S2", "S11"},
    "S4":  {"S5", "S6", "S7", "S12"},
    "S5":  {"S6", "S7", "S12"},
    # S6/S7 son la MISMA pantalla (vista individual del disco a pantalla completa; `rois.toml`
    # les da coords idénticas). Se llega con "Ver" desde varios flujos —no solo la tienda—, y
    # desde ella se puede mejorar el disco (S10):
    #   tienda:    S4 → S5 (afinación) → "Ver" → S6/S7 → "Mejorar" → S10
    #   baterías:  S13 → S21 → [auto-combate] → S22 ("Obtenido") → "Ver" → S6/S7 → S10
    #   inventario: S9 → "Ver" → S6/S7 → S10
    # Antes solo se aceptaba {S4, S6, S7}: viniendo de S22 la transición se rechazaba como FP y
    # caía a S12 ⇒ el disco no se parseaba y NO saltaba el toast (bug de QA en vivo 2026-07-16).
    "S6":  {"S7", "S12", "S4", "S5", "S9", "S10", "S22"},
    "S7":  {"S12", "S4", "S6", "S5", "S9", "S10", "S22"},
    "S8":  {"S17", "S18", "S19", "S12", "S15", "S9", "S23", "S29"},   # equipar un disco/arma de otro PJ → diálogo swap
    "S9":  {"S8", "S12", "S17", "S16", "S6", "S7", "S30"},   # "Ver" un disco del inventario → S6/S7
    # S30 (inventario de amplificadores): vecino de S9 — las pestañas de la bolsa están una al
    # lado de la otra, así que S9↔S30 es un click. Se sale al equipamiento o al detalle del arma.
    "S30": {"S9", "S12", "S8", "S26", "S15", "S1"},
    "S10": {"S12", "S9", "S3", "S20", "S6", "S7"},    # volver de la mejora a la vista individual
    # S24 = el "Obtenido" que confirma el desmontaje. S25 = el diálogo de grado S que va en el
    # medio (se detecta desde 2026-07-25 para congelar el conteo; NO commitea). Camino real:
    # S11 → S25 → S24 con grado S, o S11 → S12 → S24 sin él (sin grado S no hay diálogo).
    "S11": {"S12", "S9", "S3", "S24", "S25"},
    "S24": {"S11", "S12", "S9"},
    "S25": {"S11", "S12", "S24", "S9"},   # cancelar vuelve a la grilla; confirmar lleva al modal
    "S12": {"S1", "S2", "S4", "S8", "S9", "S10", "S11", "S13", "S14", "S15", "S16", "S3", "S5", "S6", "S7", "S17", "S18", "S19", "S20", "S21", "S22", "S23", "S24", "S27", "S28", "S29", "S30"},
    "S13": {"S12", "S14", "S1", "S18", "S21", "S22"},
    "S14": {"S12", "S1", "S13", "S15", "S18"},
    "S15": {"S8", "S18", "S19", "S12", "S14"},
    "S16": {"S12", "S9", "S8", "S18"},
    "S17": {"S8", "S18", "S19", "S12", "S15", "S9", "S23", "S26"},   # desde el detalle, sustituir un disco de otro PJ
    # S26 (detalle de W-Engine): misma familia de equipamiento que S17. Se llega desde la vista
    # del agente y se sale a los mismos lugares; el tab de armas y el de discos son vecinos, así
    # que S17↔S26 es una transición normal (el usuario alterna entre las dos).
    "S26": {"S8", "S18", "S19", "S12", "S15", "S9", "S23", "S17", "S29"},
    "S18": {"S8", "S19", "S12", "S15", "S17"},
    "S19": {"S8", "S18", "S12", "S15", "S17"},
    "S20": {"S12", "S17", "S9", "S8", "S15", "S10"},   # tras confirmar el vuelto → inventario
    # S21 (modal de usos de batería): se abre sobre S13 y se cierra a S13. El auto-combate que
    # dispara pasa por S12 antes del "Obtenido" (S22), que se cierra de vuelta a S13.
    "S21": {"S12", "S13", "S1", "S22"},
    # S22 → S6/S7: "Ver" un drop del "Obtenido" abre la vista individual (y desde ahí se mejora).
    "S22": {"S12", "S13", "S1", "S21", "S6", "S7"},
    # S23 (diálogo de sustitución): modal sobre el flujo de equipamiento. Se abre desde S8/S17 (o
    # la grilla de selección de disco, que cae a S12) y al confirmar/cancelar vuelve a ese flujo.
    "S23": {"S12", "S17", "S8", "S9"},
    # S29 (diálogo de sustitución de ARMA): el gemelo de S23 en el flujo de W-Engines. Se abre
    # desde la grilla de selección de arma (que cae a S12) o desde S26, y al confirmar/cancelar
    # vuelve al mismo flujo de equipamiento.
    "S29": {"S12", "S26", "S8", "S9", "S17"},
    # Gacha. El camino real del x10 es S27 → S12 → S28: entre el banner y la grilla va la
    # animación de recolección (la pila de televisores), que NO se modela porque es salteable y
    # no tiene datos. Que ahí diga "pantalla no reconocida" es correcto, no un bug. Se aceptan
    # igual S27↔S28 directas por si la animación se saltea tan rápido que no cae ningún frame.
    "S27": {"S12", "S28", "S1", "S15"},
    "S28": {"S12", "S27", "S1"},
}

STATE_DESCRIPTIONS: dict[str, str] = {
    "S1":  "Patrulla / menú",
    "S2":  "Resultado del desafío (lista de drops)",
    "S3":  "Modal detalle disco (desde resultado)",
    "S4":  "Tienda música — selector",
    "S5":  "Resultado de afinación",
    "S6":  "Vista individual del disco (detalle a pantalla completa)",
    "S7":  "Vista individual del disco (detalle a pantalla completa)",
    "S8":  "Equipamiento disco personaje (vista previa, sin slot abierto)",
    "S9":  "Inventario general de discos",
    "S10": "Modal upgrade disco",
    "S11": "Pantalla desmontaje",
    "S12": "Sin coincidencia (estado no reconocido / pantalla intermedia)",
    "S13": "Selección de set de discos para farmear (nodo boss) — ANTELACIÓN A CAPTURA",
    "S14": "Selección de equipo (pre-combate) — ANTELACIÓN A CAPTURA",
    "S15": "Menú de personajes (plan de entrenamiento)",
    "S16": "Detalle set de discos (modal 'Información de conjunto')",
    "S17": "Equipamiento PJ — vista detalle disco (Personalización pistas)",
    "S18": "Perfil agente — pestaña Atributos base",
    "S19": "Perfil agente — pestaña Habilidades (sin extracción)",
    "S20": "Materiales recuperados (vuelto tras mejorar disco)",
    "S21": "Modal selección de usos (baterías) — ANTELACIÓN A CAPTURA",
    "S22": "Modal 'Obtenido' (drops del farmeo por baterías)",
    "S23": "Diálogo de sustitución de disco entre PJs (confirmar swap)",
    "S29": "Diálogo de sustitución de W-Engine entre PJs (confirmar swap de arma)",
    "S30": "Inventario general de amplificadores (W-Engines)",
    "S24": "Modal 'Obtenido' — confirmación del desmontaje",
    "S25": "Diálogo de confirmación del desmontaje (selección con grado S)",
    "S26": "Equipamiento PJ — vista detalle W-Engine",
    "S27": "Canal de sintonización (banner) — ANTELACIÓN A CAPTURA",
    "S28": "Resultados de sintonización (grilla 5×2 del x10)",
}

# Estados que SÍ tienen un disco visible para parsear
CAPTURE_DISC_STATES: set[str] = {"S3", "S5", "S6", "S7", "S17"}
# Estados de upgrade (PRE/POST sync)
UPGRADE_STATES: set[str] = {"S10"}
# Estados sin disco (solo logging informativo)
NON_CAPTURE_STATES: set[str] = {
    "S1", "S2", "S4", "S8", "S9",
    "S11", "S12", "S13", "S14", "S15", "S16", "S19", "S20", "S21", "S22", "S23",
    # S11 y S24 no exponen un disco por el camino de `CAPTURE_DISC_STATES`: el panel DETAIL de
    # S11 lo lee su propio handler (que además necesita el censo de tildes para saber a QUÉ
    # celda pertenece) y S24 solo muestra materiales.
    "S24",
    # S25 es un diálogo: tapa la grilla y no expone nada parseable. Su único aporte es de flujo.
    "S25",
    # S26 muestra un W-Engine, no un disco. Está acá justamente para que el pipeline de discos
    # ni lo mire: la contaminación que `test_armas_no_contaminan_discos` documenta se evitaba
    # hasta ahora por la abstención de los parsers, y ahora además por ruteo.
    "S26",
    # Gacha: ninguna de las dos pantallas expone DISCOS, que es de lo que habla este set. S28 sí
    # tiene recompensas, pero son agentes y W-Engines y las lee su propio handler.
    "S27", "S28",
    # S29 es el diálogo de sustitución de un ARMA. Existe justamente para que el flujo de discos
    # no lo mire: mientras cayó en S23, `parser_sustitucion` intentaba leerlo, fallaba —lo
    # correcto— y dejaba un PNG de diagnóstico por cada reemplazo de arma (QA 2026-07-30).
    "S29",
    # S30 muestra AMPLIFICADORES, no discos. Mismo motivo que S26: que el pipeline de discos ni
    # lo mire. Tiene su propio handler, igual que S26.
    "S30",
}

# Estados donde hay stats de agente visibles (Atributos base)
AGENT_STATS_STATES: set[str] = {"S18"}

# Rangos HSV para glow verde del slot seleccionado en S17
# QA 2026-05-13: el aro de slot activo tiene H 45-75, S 120-255, V 180-255
_SLOT_GLOW_HSV_LOWER = np.array([40, 100, 170])
_SLOT_GLOW_HSV_UPPER = np.array([80, 255, 255])

# Posiciones de slots en la vista hexágono (S8 pantalla agente).
# Layout hexagonal de ZZZ:
#          slot1 (centro-top)
#  slot6 (izq)     slot2 (der)
#  slot5 (izq)     slot3 (der)
#          slot4 (centro-bottom)
# Calibrado desde rois.toml [agente_equipados] sobre screenshots reales.
_SLOT_POSITIONS: dict[int, tuple[float, float, float, float]] = {
    1: (0.480, 0.280, 0.080, 0.100),   # top-center
    2: (0.580, 0.350, 0.080, 0.100),   # upper-right
    3: (0.580, 0.500, 0.080, 0.100),   # lower-right
    4: (0.480, 0.570, 0.080, 0.100),   # bottom-center
    5: (0.380, 0.500, 0.080, 0.100),   # lower-left
    6: (0.380, 0.350, 0.080, 0.100),   # upper-left
}


# =========================================================================
# Tab-bar detector — familia "detalle de agente" (RF-04 §4)
# =========================================================================
# La pantalla de detalle de agente tiene 3 pestañas abajo a la derecha:
#   "Atributos base" (S18) | "Habilidades" (S19) | "Equipamiento" (S8)
# La pestaña activa es un "pill" relleno amarillo (Atributos) o amarillo-lima
# (Equipamiento). Detectar cuál está activa es una señal DETERMINISTA de en
# cuál de los 3 estados de la familia estamos — más robusta que template/HSV/
# deep-detect, que confunden S8↔S18 (cf. Dev_IA 2026-06-03).
#
# Calibrado sobre 24 capturas reales 2559×1439 (5 S8, 7 S18, 8 FP, 5 S15):
#   → 24/24 aciertos. Resolución-agnóstico (ROI + centros normalizados).
_TAB_BAR_ROI: tuple[float, float, float, float] = (0.50, 0.90, 0.45, 0.065)  # x,y,w,h norm
# Centro x normalizado (imagen completa) del pill de cada pestaña → estado:
_TAB_CENTERS: dict[str, float] = {
    "S18": 0.59,   # Atributos base (izq)
    "S19": 0.74,   # Habilidades (centro)
    "S8":  0.87,   # Equipamiento (der)
}
# Rango HSV del pill activo: cubre amarillo puro (Atributos) y amarillo-lima
# (Equipamiento, tinte según tema del PJ).
_TAB_HSV_LOWER = np.array([20, 90, 120])
_TAB_HSV_UPPER = np.array([45, 255, 255])
# Pills reales: ratio 0.22–0.28. Ruido de S15/S2 ≤ 0.082. Gate con margen amplio.
_TAB_MIN_RATIO = 0.12


# --- Avatar-row: posición del avatar seleccionado (proxy de identidad) -------
# En la familia de detalle de agente, el avatar del PJ actual está resaltado con
# un borde rombo amarillo/lima en el row superior derecho. Su posición x es un
# proxy barato y robusto de "qué PJ" — si cambia de slot, cambió el PJ. Útil para
# detectar cambio de agente en S8/S19 (sin nombre en pantalla) sin necesitar aún
# el matcher de avatar completo (Etapa 2). Calibrado sobre capturas reales.
_AVATAR_ROW_ROI: tuple[float, float, float, float] = (0.55, 0.005, 0.42, 0.075)  # x,y,w,h norm
_AVATAR_HL_LOWER = np.array([20, 90, 120])   # borde amarillo/lima del seleccionado
_AVATAR_HL_UPPER = np.array([45, 255, 255])
_AVATAR_HL_MIN_PIXELS = 30   # mínimo de columnas-equivalentes con highlight
# Fracción del lado del tile resaltado que se recorta como "cara" (sin el borde).
_AVATAR_FACE_INNER = 0.42


def selected_avatar_x(frame: np.ndarray) -> float | None:
    """
    Devuelve la posición x normalizada (0-1, imagen completa) del avatar
    resaltado en el row superior, o None si no hay highlight claro.

    Es un proxy de identidad: el mismo PJ mantiene su x; un cambio de x ⇒ se
    seleccionó otro PJ. No identifica QUIÉN (eso es el matcher de avatar), solo
    detecta cambios. Pura HSV, sin OCR, ~1 ms.
    """
    if frame is None or frame.size == 0:
        return None
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _AVATAR_ROW_ROI
        x0, y0 = int(x * w), int(y * h)
        x1, y1 = int((x + rw) * w), int((y + rh) * h)
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _AVATAR_HL_LOWER, _AVATAR_HL_UPPER)
        cols = mask.sum(axis=0)
        total = cols.sum()
        if total < 255 * _AVATAR_HL_MIN_PIXELS:
            return None
        cx = int((np.arange(len(cols)) * cols).sum() / total)
        return (x0 + cx) / w
    except Exception:
        return None


def crop_selected_avatar(frame: np.ndarray) -> np.ndarray | None:
    """
    Recorta la cara del avatar resaltado (el PJ actual) para identificación.

    Aísla el tile seleccionado por el **componente conexo más grande** del borde
    amarillo/lima (evita capturar el amarillo de tiles vecinos), toma el centro
    de su bounding box y recorta la región interior de la cara. Devuelve el crop
    BGR (cuadrado) o None si no hay highlight claro.

    Validado: dos crops del MISMO PJ en pestañas distintas (S18 vs S8) correlan
    ~0.995; PJs distintos ≤ ~0.72. Base del matcher de avatar (bootstrap desde S18).
    """
    if frame is None or frame.size == 0:
        return None
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _AVATAR_ROW_ROI
        x0, y0 = int(x * w), int(y * h)
        sub = frame[y0:int((y + rh) * h), x0:int((x + rw) * w)]
        if sub.size == 0:
            return None
        hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _AVATAR_HL_LOWER, _AVATAR_HL_UPPER)
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n <= 1:
            return None
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        bx, by, bw, bh, area = stats[idx]
        if area < 200:
            return None
        cx, cy = bx + bw // 2, by + bh // 2
        side = int(min(int(bw), int(bh)) * _AVATAR_FACE_INNER)
        if side < 8:
            return None
        fx0 = max(0, x0 + cx - side)
        fy0 = max(0, y0 + cy - side)
        face = frame[fy0:fy0 + 2 * side, fx0:fx0 + 2 * side]
        return face if face.size else None
    except Exception:
        return None


# --- Badge de dueño del tile seleccionado en la grilla S17 (Fase 5R) ----------
# En la vista de detalle de disco (S17), la columna izquierda es una grilla de
# discos candidatos; cada tile EQUIPADO lleva en su esquina sup-der un retrato
# circular del PJ dueño. El tile SELECCIONADO está resaltado (mismo borde
# amarillo/lima que el row). Localizamos ese tile por highlight y recortamos su
# badge con offset FIJO (calibrado sobre frames reales 2026-06-10): el badge
# cuelga de la esquina sup-der. centro=(tx+0.86·tw, ty+0.13·th), radio≈0.18·tw.
_GRID_REGION = (0.01, 0.10, 0.235, 0.95)        # x0,y0,x1,y1 norm (columna grilla S17)
# Grilla del INVENTARIO GLOBAL S9: ocupa casi todo el ancho (8 columnas) menos el panel
# derecho. El tile seleccionado tiene el MISMO indicador (aro lima/amarillo) y MISMO badge
# de dueño en la esquina sup-der → se reusa toda la maquinaria con esta región (verificado
# 2026-06-21: tile cuadrado w≈0.069 h≈0.122 fill 0.16, dentro de los filtros S17).
_S9_GRID_REGION = (0.01, 0.10, 0.70, 0.95)
_BADGE_CX_F, _BADGE_CY_F, _BADGE_R_F = 0.86, 0.13, 0.18
_GRID_TILE_MIN_AREA = 1200
# Filtro de forma del anillo de selección (calibrado sobre frames reales 2026-06-11):
# tile ~175×172 px @ 2559×1439 → ~0.068·W × ~0.119·H. Aro hueco (fill 0.07–0.18);
# barras "Nivel" llenas (fill ~0.63) → excluidas por _TILE_FILL_MAX.
_TILE_W_FRAC = np.array([0.052, 0.088])     # [min,max] ancho / W
_TILE_H_FRAC = np.array([0.095, 0.140])     # [min,max] alto / H
_TILE_ASPECT_MIN, _TILE_ASPECT_MAX = 0.78, 1.28
_TILE_FILL_MAX = 0.45

# Gate de PRESENCIA del badge del grid (5R.L.7.2): un tile EQUIPADO lleva un retrato
# circular del dueño en la esquina; un tile LIBRE NO (arte/candado/oscuro). El crop de
# offset fijo (crop_grid_selected_badge) no distinguía → en libres recortaba la esquina
# vacía y el matcher la votaba a un PJ (falso "Cissia", QA 2026-06-20 → viola RNF-02).
# Gate = el avatar real tiene (a) un ANILLO (Hough) + (b) un blob saturado. Calibrado sobre
# 218 esquinas equipadas (audit/free_disc_presence_diag.md): hough≥1 en 218/218, blob≥245.
# Umbral de área 150 (margen bajo el piso 245 → 0 regresión en equipados). El lado LIBRE
# (no validable offline) lo respalda el árbitro del detail; se afina en QA en vivo.
_GRID_BADGE_SAT_MIN = 50                       # saturación del blob de avatar (== _DET_SAT_MIN)
_GRID_BADGE_MIN_AREA = 150                     # área mín del blob saturado (px)
_GRID_BADGE_HOUGH_RMIN_F = 0.30                # radio mín del anillo / lado del crop
_GRID_BADGE_HOUGH_RMAX_F = 0.60                # radio máx del anillo / lado del crop

# Detalle-badge (5R.C.4): avatar del dueño junto a 'Nivel 15/15' del panel de detalle.
# Localización MUCHO más robusta que el grid-tile (100% vs 73% en video): fija en X
# (~0.495), fondo oscuro (sin confound de arte amarillo), siempre presente (sin NOLOC de
# transición). Robusto al corrimiento en Y (nombre 1 vs 2 líneas) localizando el blob
# saturado en la franja. Encuadre DISTINTO al grid-badge → librería propia (avatar_detbadge).
_DET_REGION = (0.475, 0.515, 0.12, 0.26)     # x0,x1,y0,y1 norm (franja del detalle-badge)
_DET_SAT_MIN = 50                            # saturación mínima (avatar colorido vs texto blanco)
_DET_MIN_AREA = 200
# Refine L.2b (5R, 2026-06-17): el crop con radio FIJO (_DET_R_F·W ≈ 96 px) dejaba al
# avatar (~55 px) ahogado en fondo a rayas IDÉNTICO por página → el descriptor se agrupaba
# por fondo → imán correlacionado con la página (audit/detbadge_magnet_diag_20260617.md).
# Fix: localizar el CÍRCULO real del avatar por Hough dentro de la franja y recortar ajustado
# a la cara (excluye el fondo). Cross-domain (page≠dueño): 20%→91% top-1, 0 wrong, imán
# eliminado. El radio fijo queda solo como referencia histórica (no se usa).
_DET_HOUGH_RMIN_F = 0.008                     # radio mín del avatar / W
_DET_HOUGH_RMAX_F = 0.015                     # radio máx del avatar / W
# `_DET_HOUGH_PAD` (1.05) vivía acá y daba el margen sobre el radio de Hough. Se eliminó el
# 2026-08-14 junto con el radio detectado: ya no hay nada a lo que ponerle margen.

# Radio del RECORTE, como fracción de W. **Hough LOCALIZA, esta constante ENCUADRA** (2026-08-14).
#
# Esto NO es volver al radio fijo que falló en 2026-06-17. Aquel era `_DET_R_F·W ≈ 96 px` para un
# avatar de ~55: ahogaba la cara en fondo a rayas y el descriptor se agrupaba por página. La
# lección de entonces fue *no recortar ancho*, no *no usar una constante*; lo de acá es una
# constante AJUSTADA a la cara, con el centro que Hough ya resuelve bien.
#
# El badge es un elemento de UI de tamaño fijo, así que detectar su radio solo mete varianza.
# Medido sobre los 95 badges localizados en los fixtures (S17 grilla/slots/inventario + S26): el
# radio se concentra en 23-25 —81 de 95— pero se va a 29-37 en una decena. Esos son los que
# recortan flojo, y si pasa mientras se COSECHA la ref queda envenenada para siempre: es el caso
# de Zhao, cuyas refs matchean mejor con encuadre ancho que ajustado.
#
# Barrido con la distancia al mejor match como métrica (misma que en `_S30_OWNER_R_F`):
#
#     hoy    dist media 0.128 · bajo 0.15: 67/95 · nombrados 61
#     r=25   dist media 0.118 · bajo 0.15: 74/95 · nombrados 64   ← elegido
#     r=26   dist media 0.127 · bajo 0.15: 74/95 · nombrados 66
#
# Es un CLAMP de outliers más que un re-encuadre: 25 es casi lo que el código ya producía para el
# caso modal (24 × 1.05 = 25.2). Por eso la ganancia es modesta —y por eso es segura: en los 95
# badges, CERO cambian de identificación. Esto importa porque este crop decide el dueño en S17 y
# ese dueño alimenta `sync_equip`, que ESCRIBE la DB.
_DET_CROP_R_F = 25.0 / 2559.0


def _selected_grid_tile_bbox(frame: np.ndarray, region: tuple = _GRID_REGION):
    """Bbox (en frame) del tile resaltado de la grilla, o None. `region` = la grilla
    a inspeccionar (S17 columna izq por default; `_S9_GRID_REGION` para el inventario).

    El indicador es un ANILLO (aro lima/amarillo) alrededor del tile seleccionado:
    bbox ~cuadrado del tamaño del tile y HUECO (poca área de píxeles vs su bbox).
    NO se puede usar `argmax(área)` crudo: el arte dorado de los sets Jazz y las
    barras de "Nivel 15" (amarillas, anchas y llenas) tienen MÁS área que el anillo
    y ganaban → bbox degenerado (143×28) → recorte de badge inservible → INCIERTO
    falso (diag 2026-06-11). Se filtra por FORMA: cuadrado (aspect≈1), tamaño de
    tile (~0.068·W) y bajo factor de relleno (hueco). De los candidatos válidos se
    toma el de mayor área (anillo completo > fragmento parcial)."""
    if frame is None or frame.size == 0:
        return None
    try:
        H, W = frame.shape[:2]
        x0, y0, x1, y1 = region
        gx0, gy0 = int(x0 * W), int(y0 * H)
        sub = frame[gy0:int(y1 * H), gx0:int(x1 * W)]
        if sub.size == 0:
            return None
        mask = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), _AVATAR_HL_LOWER, _AVATAR_HL_UPPER)
        n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
        if n <= 1:
            return None
        # Ventana de tamaño de tile, en fracción del frame (robusto a resolución).
        wmin, wmax = _TILE_W_FRAC * W
        hmin, hmax = _TILE_H_FRAC * H
        best = None  # (area, bx, by, bw, bh)
        for i in range(1, n):
            bx, by, bw, bh, area = stats[i]
            if area < _GRID_TILE_MIN_AREA or bw < 1 or bh < 1:
                continue
            aspect = bw / bh
            fill = area / float(bw * bh)
            if not (wmin <= bw <= wmax and hmin <= bh <= hmax):
                continue
            if not (_TILE_ASPECT_MIN <= aspect <= _TILE_ASPECT_MAX):
                continue
            if fill > _TILE_FILL_MAX:        # lleno = arte de disco / barra, no anillo
                continue
            if best is None or area > best[0]:
                best = (area, bx, by, bw, bh)
        if best is None:
            return None
        _a, bx, by, bw, bh = best
        return gx0 + bx, gy0 + by, bw, bh
    except Exception:
        return None


def _grid_badge_present(crop: np.ndarray | None) -> bool:
    """¿El crop de esquina del tile contiene un AVATAR de dueño (equipado) y no una
    esquina vacía/arte/candado (libre)? (5R.L.7.2). Un avatar real = anillo circular
    (Hough) + blob saturado. Sin ambos → no hay dueño → el grid no debe votar (RNF-02:
    evita el falso 'Cissia' en discos libres). Calibrado en audit/free_disc_presence_diag.md
    para 0 regresión en 218 equipados; el lado libre lo respalda el árbitro del detail."""
    if crop is None or crop.size == 0:
        return False
    try:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 1] > _GRID_BADGE_SAT_MIN).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
        if n <= 1 or int(stats[1:, 4].max()) < _GRID_BADGE_MIN_AREA:
            return False                      # sin blob saturado → esquina vacía/oscura
        h = crop.shape[0]
        gray = cv2.medianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 3)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=h, param1=120, param2=18,
            minRadius=int(_GRID_BADGE_HOUGH_RMIN_F * h), maxRadius=int(_GRID_BADGE_HOUGH_RMAX_F * h),
        )
        return circles is not None             # anillo del avatar presente
    except Exception:
        return False


def crop_grid_selected_badge(frame: np.ndarray, region: tuple = _GRID_REGION) -> np.ndarray | None:
    """Recorta (círculo) el badge de dueño del tile seleccionado de la grilla.
    Devuelve el crop BGR o None si no hay tile resaltado O si el tile NO tiene avatar
    de dueño (disco LIBRE → gate de presencia, 5R.L.7.2). Es el ícono que el matcher
    de badge identifica para saber QUÉ PJ tiene equipado el disco. `region` selecciona
    la grilla (S17 izq por default; `_S9_GRID_REGION` para el inventario global)."""
    bb = _selected_grid_tile_bbox(frame, region)
    if bb is None:
        return None
    tx, ty, tw, th = bb
    cx, cy, r = int(tx + _BADGE_CX_F * tw), int(ty + _BADGE_CY_F * th), int(_BADGE_R_F * tw)
    if r < 8:
        return None
    H, W = frame.shape[:2]
    crop = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    if not crop.size or not _grid_badge_present(crop):
        return None                            # tile sin avatar = disco libre → NOLOC
    return crop


# --- S9: LIBRE vs NO SÉ ------------------------------------------------------------------------
# El badge del tile responde tres cosas distintas y hasta 2026-08-18 las dos últimas salían iguales
# (`None`), que es lo que bloqueaba el censo: 72 de 367 discos no tienen dueño, y sin poder AFIRMAR
# "está libre" no se los puede persistir sin arriesgar un equipamiento inventado.
BADGE_CON_DUENO = "con_dueno"        # hay una cara en la esquina del tile
BADGE_LIBRE = "libre"                # se leyó la esquina y NO hay nadie
BADGE_NO_LOCALIZADO = "no_localizado"  # no se pudo leer (sin tile resaltado) — NO es lo mismo

# Presencia por NITIDEZ (|Laplaciano| medio del disco interior), no por saturación.
# `_grid_badge_present` (blob saturado + Hough) da True en los 4 libres de
# `09_Inventario_discos_general`: la esquina libre tiene barra de nivel amarilla + arte gris, con
# saturación y circularidad de sobra. Es el mismo hallazgo de S17
# (audit/free_disc_presence_validation_20260620.md: "no existe umbral que la separe") y de RF-15 en
# armas ("el área saturada SE SOLAPA"). La nitidez mide otra cosa: una cara tiene detalle, un
# degradé no tiene ninguno.
#
# Medido sobre los 11 tiles etiquetados:   equipado 55.89-81.44   ·   libre 12.51-15.70   (3.56×)
# Sobre los 504 tiles de la grilla completa la distribución es bimodal y la franja 20-35 está
# VACÍA. Por eso 30 no es un umbral al borde: cae en el medio del hueco.
_S9_BADGE_NITIDEZ_MIN = 30.0
_S9_BADGE_DISCO_F = 0.55             # fracción del lado usada como disco interior


@dataclass(frozen=True)
class GridBadge:
    """Lectura del badge de dueño de un tile de grilla, con el PORQUÉ cuando no hay recorte."""

    estado: str                       # BADGE_CON_DUENO | BADGE_LIBRE | BADGE_NO_LOCALIZADO
    nitidez: float | None = None      # la evidencia; None si no hubo dónde medir
    crop: np.ndarray | None = None    # solo con dueño — es lo que el matcher nombra


def _badge_nitidez(crop: np.ndarray) -> float:
    """|Laplaciano| medio dentro del disco interior del recorte."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w]
    disco = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) < (_S9_BADGE_DISCO_F * min(h, w) / 2) ** 2
    return float(np.abs(cv2.Laplacian(g, cv2.CV_32F))[disco].mean())


def read_s9_selected_badge(frame: np.ndarray) -> GridBadge:
    """Badge del tile seleccionado del inventario global S9, distinguiendo los tres desenlaces.

    Nunca lanza: ante cualquier fallo devuelve `BADGE_NO_LOCALIZADO`, que es la respuesta honesta
    —no se pudo leer— y la única que no habilita ninguna escritura.
    """
    try:
        if frame is None or frame.size == 0:
            return GridBadge(BADGE_NO_LOCALIZADO)
        bb = _selected_grid_tile_bbox(frame, _S9_GRID_REGION)
        if bb is None:
            return GridBadge(BADGE_NO_LOCALIZADO)
        tx, ty, tw, th = bb
        cx = int(tx + _BADGE_CX_F * tw)
        cy = int(ty + _BADGE_CY_F * th)
        r = int(_BADGE_R_F * tw)
        if r < 8:
            return GridBadge(BADGE_NO_LOCALIZADO)
        H, W = frame.shape[:2]
        crop = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
        if not crop.size:
            return GridBadge(BADGE_NO_LOCALIZADO)
        nit = _badge_nitidez(crop)
        if nit < _S9_BADGE_NITIDEZ_MIN:
            # Se leyó la esquina y no hay cara. Sin recorte a propósito: devolverlo invitaría al
            # matcher a nombrar el arte del disco (el falso "Cissia" de los libres, 5R.L.7.2).
            return GridBadge(BADGE_LIBRE, nitidez=nit)
        return GridBadge(BADGE_CON_DUENO, nitidez=nit, crop=crop)
    except Exception:
        return GridBadge(BADGE_NO_LOCALIZADO)


def crop_s9_selected_badge(frame: np.ndarray) -> np.ndarray | None:
    """Badge de dueño del tile seleccionado del INVENTARIO GLOBAL S9 (esquina sup-der,
    a la derecha del nº de slot). Reusa `crop_grid_selected_badge` con la región S9.
    El badge es del mismo tipo que el de S17 → mismo matcher/librería (avatar_badge_v2).

    Vista de un solo campo de `read_s9_selected_badge`: mismo contrato de siempre (recorte o None),
    pero la presencia la decide la NITIDEZ y no el gate por saturación, que en S9 daba positivo en
    los 4 discos libres medidos. Quien necesite saber POR QUÉ es None usa el lector completo."""
    return read_s9_selected_badge(frame).crop


# --- S9: el avatar del dueño en el PANEL DE DETALLE (segunda superficie) -----------------------
# La grilla no alcanza para nombrar. Medido el 2026-08-18: en la superficie `grid`, Ben y Soukaku
# están separados 1,04-1,14× (las refs de Ben están casi tan dispersas entre sí como respecto a
# Soukaku), así que un disco de Soukaku empata 0.897/0.897 con margen 0.000 y el matcher se
# abstiene — correctamente, porque con esos datos no puede decidir. En la superficie `detail` la
# separación por histograma de color es 8,87×.
#
# ROI: SOLO la mitad derecha de la banda superior del panel. La zona tiene tres círculos y dos son
# señuelos:
#     hexágono del nº de slot   izquierda   sat ~12
#     badge dorado de rareza    abajo       sat ~119   ← el MÁS saturado de la zona
#     avatar del dueño          derecha     sat ~58
# Elegir "el más saturado" agarra siempre el de rareza: daba 0.47 constante en los 14 fixtures,
# incluidos los libres que no tienen avatar. El discriminador es la POSICIÓN.
#
# La banda es alta (0.310-0.372) a propósito: el panel se corre verticalmente cuando el nombre del
# set envuelve a dos líneas (medido: el avatar cae en y=29 o y=51 dentro de la zona según el caso).
_S9_DET_REGION = (0.752, 0.788, 0.310, 0.372)      # x0, x1, y0, y1 normalizados

# Radio del recorte, CONSTANTE. El avatar es un elemento de UI de tamaño fijo y detectarlo sólo
# mete varianza (misma lección que `_DET_CROP_R_F` en S17 y `_S30_OWNER_R_F` en S30). Medido sobre
# el badge de Soukaku: con r=18 nombra a 0.843; con 22, 25, 26 o 30 se abstiene. Es más chico que
# el de S17 (25 px) porque este panel es más angosto.
_S9_DET_R = 18


def crop_s9_detail_badge(frame: np.ndarray) -> np.ndarray | None:
    """Avatar del dueño en el panel de detalle del inventario S9, o `None` si no hay.

    Segunda superficie para nombrar: la grilla y ésta **coinciden siempre que las dos hablan**
    (verificado sobre los 14 fixtures, 0 desacuerdos) y el detalle resuelve casos que la grilla
    pierde — tile no localizado, o abstención por look-alike.

    `None` significa "no hay avatar en el panel", que para un disco es señal de que nadie lo tiene
    equipado. No se usa para AFIRMAR libre por sí sola: esa decisión sigue en manos del gate de
    nitidez de la grilla (ver `read_s9_selected_badge`), y la regla del proyecto es que la
    PRESENCIA gana a LIBRE.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        H, W = frame.shape[:2]
        fx0, fx1, fy0, fy1 = _S9_DET_REGION
        x0, x1, y0, y1 = int(fx0 * W), int(fx1 * W), int(fy0 * H), int(fy1 * H)
        sub = frame[y0:y1, x0:x1]
        if sub.size == 0:
            return None
        gray = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 3)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=25, param1=120, param2=18,
            minRadius=14, maxRadius=30,
        )
        if circles is None:
            return None
        cx, cy = int(circles[0][0][0]), int(circles[0][0][1])
        gx, gy = x0 + cx, y0 + cy
        r = _S9_DET_R
        crop = frame[max(0, gy - r):min(H, gy + r), max(0, gx - r):min(W, gx + r)]
        if crop.shape[0] != 2 * r or crop.shape[1] != 2 * r:
            return None            # recorte contra el borde: mejor abstenerse que deformar
        return crop
    except Exception:
        return None


def crop_detail_badge(frame: np.ndarray) -> np.ndarray | None:
    """Recorta (círculo) el avatar del dueño del PANEL DE DETALLE S17 (junto a 'Nivel
    15/15'). Two-stage (5R.L.2b): (1) franja fija del header como recorte grueso + gate
    de presencia (blob saturado = hay avatar; sin él → disco sin dueño → None); (2) Hough
    localiza el CENTRO del avatar y se recorta AJUSTADO a la cara con `_DET_CROP_R_F`,
    excluyendo el fondo a rayas que antes ahogaba al descriptor (imán por página, ver
    audit/detbadge_magnet_diag_20260617.md). Encuadre propio → librería avatar_detbadge_v2.

    **El radio no sale de Hough**: es un elemento de UI de tamaño fijo y detectarlo solo metía
    varianza — ver `_DET_CROP_R_F` para los números y para por qué esto no es volver al radio
    fijo de junio.
    None si no hay avatar (disco libre) o si Hough no halla el círculo (abstención segura;
    el voto multi-frame cubre el frame perdido — RNF-02)."""
    if frame is None or frame.size == 0:
        return None
    try:
        H, W = frame.shape[:2]
        x0, x1, y0, y1 = _DET_REGION
        sub = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        if sub.size == 0:
            return None
        # (1) gate de presencia: ¿hay un avatar (blob saturado) en la franja? Un disco
        # SIN dueño tiene fondo oscuro sin avatar → sin blob → None (no inventamos dueño).
        hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 1] > _DET_SAT_MIN).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
        if n <= 1 or stats[1:, 4].max() < _DET_MIN_AREA:
            return None
        # (2) Hough sobre la franja → círculo del avatar → crop ajustado a la cara.
        gray = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 3)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(0.05 * W),
            param1=120, param2=22,
            minRadius=int(_DET_HOUGH_RMIN_F * W), maxRadius=int(_DET_HOUGH_RMAX_F * W),
        )
        if circles is None:
            return None
        c0 = circles[0][0]
        cx, cy = int(x0 * W + c0[0]), int(y0 * H + c0[1])
        # Del círculo detectado se usa solo el CENTRO; el radio sale de `_DET_CROP_R_F`.
        r = int(_DET_CROP_R_F * W)
        if r < 8:
            return None
        crop = frame[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
        return crop if crop.size else None
    except Exception:
        return None


def detect_active_tab(frame: np.ndarray) -> str | None:
    """
    Detecta qué pestaña del detalle de agente está activa por el pill amarillo/lima.

    Devuelve el código de estado de la familia ("S18"/"S19"/"S8") o None si no
    hay un pill claro en la franja del tab-bar (⇒ no estamos en la familia, o no
    es concluyente). Pura HSV, sin OCR, ~1 ms.
    """
    if frame is None or frame.size == 0:
        return None
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _TAB_BAR_ROI
        x0, y0 = int(x * w), int(y * h)
        x1, y1 = int((x + rw) * w), int((y + rh) * h)
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _TAB_HSV_LOWER, _TAB_HSV_UPPER)
        ratio = mask.sum() / 255 / mask.size
        if ratio < _TAB_MIN_RATIO:
            return None
        cols = mask.sum(axis=0)
        total = cols.sum()
        if total <= 0:
            return None
        cx = int((np.arange(len(cols)) * cols).sum() / total)
        fullx = (x0 + cx) / w
        return min(_TAB_CENTERS, key=lambda k: abs(_TAB_CENTERS[k] - fullx))
    except Exception:
        return None


# =========================================================================
# Temporal Buffer — majority voting multi-frame
# =========================================================================

class TemporalBuffer:
    """
    Rolling window de las últimas N clasificaciones.
    Solo emite un estado cuando la mayoría de frames coincide.
    Elimina FPs transitorios de un solo frame ruidoso.

    window_size: 3 por defecto (requiere 2/3 para confirmar).
    S12 requiere consenso total (3/3) para evitar quedar pegado en
    "no match" durante transiciones.
    """

    def __init__(self, window_size: int = 3):
        self._window: list[ScreenState] = []
        self._window_size = window_size
        self._last_emitted: str | None = None
        self._last_voted: ScreenState | None = None

    @property
    def last_emitted(self) -> str | None:
        return self._last_emitted

    def add(self, state: ScreenState) -> ScreenState | None:
        """
        Agrega una clasificación al buffer.
        Devuelve un ScreenState confirmado si hay mayoría, o None si aún
        no hay suficiente consenso o es el mismo estado ya emitido.
        """
        self._window.append(state)
        if len(self._window) > self._window_size:
            self._window = self._window[-self._window_size:]

        if len(self._window) < self._window_size:
            return None  # buffer llenándose

        from collections import Counter
        codes = Counter(s.code for s in self._window)
        winner_code, count = codes.most_common(1)[0]

        # Majority needed es ceil(window_size/2), ej 2/3 o 3/5
        # S12 usa el mismo threshold (no requiere consenso total)
        majority_needed = (self._window_size // 2) + 1

        if count < majority_needed:
            return None  # sin mayoría clara

        # No re-emitir si es el mismo estado que ya emitimos
        if winner_code == self._last_emitted:
            return None

        self._last_emitted = winner_code

        winner_states = [s for s in self._window if s.code == winner_code]
        avg_conf = sum(s.confidence for s in winner_states) / len(winner_states)
        best = max(winner_states, key=lambda s: s.confidence)
        best.confidence = round(avg_conf, 3)
        self._last_voted = best
        return best

    def reset(self) -> None:
        """Limpia el buffer. Útil tras transiciones rápidas."""
        self._window.clear()
        self._last_emitted = None
        self._last_voted = None

    def promote_now(self, state: ScreenState) -> ScreenState | None:
        """
        Emite un estado inmediatamente, saltando la votación 2/3.
        Útil para detecciones de alta confianza (e.g. deep_detect S18) que
        no deben esperar 3 frames para confirmarse. Mantiene `_last_emitted`
        coherente para evitar re-emisiones del mismo estado (devuelve None
        si ya emitimos ese código previamente, igual que `add`).
        """
        self._window.append(state)
        if len(self._window) > self._window_size:
            self._window = self._window[-self._window_size:]
        if self._last_emitted == state.code:
            return None
        self._last_emitted = state.code
        self._last_voted = state
        return state


# =========================================================================
# State machine
# =========================================================================

class StateMachine:
    """Valida transiciones entre estados para reducir FPs."""

    def __init__(self):
        self._prev_code: str | None = None

    @property
    def prev_code(self) -> str | None:
        return self._prev_code

    def validate(self, detected_code: str) -> str:
        """
        Retorna `detected_code` si la transición es válida, S12 si no.
        Actualiza el estado interno tras validar.
        """
        valid = _VALID_TRANSITIONS.get(self._prev_code, _VALID_TRANSITIONS.get(None, set()))
        if detected_code in valid:
            self._prev_code = detected_code
            return detected_code
        # Si es S12 (no_match), siempre es válido (transición neutra)
        if detected_code == "S12":
            return detected_code
        # Log: transición inválida detectada (para diagnóstico)
        return detected_code  # permitimos igual para no bloquear, pero logged
        # Versión estricta (comentar si da FPs):
        # self._prev_code = "S12"
        # return "S12"

    def reset(self) -> None:
        self._prev_code = None


# =========================================================================
# Data classes
# =========================================================================

@dataclass
class ScreenState:
    """Resultado de la clasificación del frame."""
    code: str           # S1-S18
    confidence: float   # 0-1 (del template match)
    template_name: str  # nombre del template que disparó el match
    slot: int | None = None  # slot detectado 1-6 (S17/S9)
    verification: str | None = None  # resultado de verificación secundaria
    method: str = "template"  # método que clasificó: template | hsv | fusion


# =========================================================================
# Funciones de verificación secundaria por estado
# =========================================================================

# Rarezas de disco (gold S / purple A / blue B) en HSV OpenCV — para verificar que el modal S3
# muestra un DISCO (su ícono siempre tiene una franja/badge de color de rareza).
_S3_RARITY_BANDS = (
    ((14, 120, 120), (36, 255, 255)),    # dorado (S)
    ((125, 80, 80), (155, 255, 255)),    # púrpura (A)
    ((98, 90, 90), (120, 255, 255)),     # azul (B)
)


def _verify_s3(frame: np.ndarray) -> tuple[bool, str | None]:
    """S3: verificar que el modal muestra un DISCO (ícono con franja/badge de rareza) y no otro
    modal (recompensa diaria, etc.). Mide la FRACCIÓN de píxeles de color de rareza (gold/purple/
    blue) en el ROI del ícono del disco (arriba-derecha del modal).

    FIX 2026-07: la versión vieja promediaba el HUE de un ROI mal ubicado (0.60-0.75, 0.45-0.60,
    DEBAJO del ícono) y exigía mean_hue∈[15,40]∪[130,160]. El promedio del ventilador azul + arte
    + fondo oscuro caía fuera de rango en 9/10 modales S3 reales → falsos negativos → el disco NO
    se reconocía en vivo (S3 degradaba a S12). El ROI corregido + fracción de rareza da 0.029-0.066
    en los 10 fixtures reales; umbral 0.015 (margen holgado). Sin OCR (RNF-06)."""
    try:
        h, w = frame.shape[:2]
        icon_roi = frame[int(0.19 * h):int(0.44 * h), int(0.53 * w):int(0.68 * w)]
        if icon_roi.size == 0:
            return True, None
        hsv = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2HSV)
        mask = np.zeros(icon_roi.shape[:2], np.uint8)
        for lo, hi in _S3_RARITY_BANDS:
            mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        frac = float(mask.mean()) / 255.0
        return (frac >= 0.015, f"rarity_frac={frac:.3f}")
    except Exception:
        return True, None


def _verify_s10(frame: np.ndarray) -> tuple[bool, str | None]:
    """S10: confirmar el modal de upgrade de forma NIVEL-INDEPENDIENTE.

    El check viejo exigía una barra EXP VERDE (H~45-85) en el centro, pero a nivel 0 el
    pill de nivel es GRIS (no verde) → rechazaba S10 reales recién abiertos. Además apuntaba
    a una zona que no corresponde al layout actual (panel corrido a la derecha). El template
    nuevo (barra de botones "Añadir todo | Mejorar") ya separa S10 de todo lo demás con margen
    enorme (S10 ≥0.85 vs NON ≤0.50), así que acá basta una confirmación estructural barata que
    valga en CUALQUIER nivel: la barra de nivel chevron ocupa una franja clara y saturada en
    y≈0.51 del panel derecho (gris a nivel 0, verde si >0). Se acepta si hay suficiente
    contenido brillante (no-fondo) ahí; nunca bloquea por color."""
    try:
        h, w = frame.shape[:2]
        bar = frame[int(0.495 * h):int(0.535 * h), int(0.49 * w):int(0.84 * w)]
        if bar.size == 0:
            return True, None
        gray = cv2.cvtColor(bar, cv2.COLOR_BGR2GRAY)
        # La barra chevron (pills + texto) es notablemente más clara que el fondo del modal.
        bright_ratio = float((gray > 90).mean())
        if bright_ratio > 0.12:
            return True, "barra_nivel"
        return True, "s10_template"   # el template ya es autoritativo; no bloquear
    except Exception:
        return True, None


def _verify_s17(frame: np.ndarray) -> tuple[bool, str | None]:
    """S17: verificar presencia de hexágono o grilla de stats."""
    try:
        h, w = frame.shape[:2]
        # Zona del panel de stats (centro-derecha)
        stats_roi = frame[
            int(0.25 * h):int(0.55 * h),
            int(0.30 * w):int(0.60 * w)
        ]
        if stats_roi.size == 0:
            return True, None
        gray = cv2.cvtColor(stats_roi, cv2.COLOR_BGR2GRAY)
        # Buscar líneas horizontales (separadores de substats)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 30, minLineLength=30, maxLineGap=5)
        if lines is not None and len(lines) >= 2:
            return True, f"{len(lines)}_lineas_stat"
        return False, "sin_grid_stats"
    except Exception:
        return True, None


def _s18_visual_tab_amarillo(frame: np.ndarray) -> tuple[bool, str | None]:
    """Indicador visual: subrayado amarillo del tab 'Atributos base'."""
    try:
        h, w = frame.shape[:2]
        tab_roi = frame[int(0.05 * h):int(0.12 * h), int(0.30 * w):int(0.70 * w)]
        if tab_roi.size == 0:
            return False, None
        hsv_tab = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2HSV)
        yellow_mask = cv2.inRange(hsv_tab, np.array([15, 100, 100]), np.array([40, 255, 255]))
        yellow_ratio = yellow_mask.sum() / yellow_mask.size / 255
        if yellow_ratio > 0.02:
            return True, "tab_amarillo"
        return False, None
    except Exception:
        return False, None


def _s18_visual_grilla_stats(frame: np.ndarray) -> tuple[bool, str | None]:
    """Indicador visual: grilla de stats (4+ líneas separadoras horizontales)."""
    try:
        h, w = frame.shape[:2]
        stats_roi = frame[int(0.20 * h):int(0.55 * h), int(0.15 * w):int(0.85 * w)]
        if stats_roi.size == 0:
            return False, None
        gray = cv2.cvtColor(stats_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 120)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 40,
                                minLineLength=int(0.3 * stats_roi.shape[1]),
                                maxLineGap=8)
        if lines is None:
            return False, None
        ys = sorted(set(l[0][1] for l in lines))
        if len(ys) < 4:
            return False, None
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        uniform_gaps = sum(1 for g in gaps if abs(g - avg_gap) < 10)
        if uniform_gaps >= len(gaps) * 0.5:
            return True, f"grid_{len(ys)}_stats"
        return False, None
    except Exception:
        return False, None


def _s18_visual_valores_brillantes(frame: np.ndarray) -> tuple[bool, str | None]:
    """Indicador visual: zona de valores numéricos brillantes en columna derecha."""
    try:
        h, w = frame.shape[:2]
        val_roi = frame[int(0.22 * h):int(0.50 * h), int(0.65 * w):int(0.80 * w)]
        if val_roi.size == 0:
            return False, None
        gray_val = cv2.cvtColor(val_roi, cv2.COLOR_BGR2GRAY)
        bright = (gray_val > 150).sum() / gray_val.size
        if bright > 0.20:
            return True, "valores_brillantes"
        return False, None
    except Exception:
        return False, None


def _s18_visual_agent_info_clahe(frame: np.ndarray) -> tuple[bool, str | None]:
    """
    Indicador visual: 'AGENT INFO' texto sutil detectado por CLAHE + threshold.

    Calibración empírica (QA 2026-05-15):
      - S18 fixtures reales (2559×1439): std 38-103, text_area 0.50-0.74
      - FPs modal Info conjunto (S16):    std  7-8,  text_area 1.00
      - Frame negro/carga uniforme:       std  0,    text_area 1.00

    Filtros aplicados:
      - std > 15 → descarta regiones uniformes oscuras (FPs S16, cargas)
      - 0.03 < text_area < 0.95 → descarta frames totalmente oscuros
    """
    try:
        h, w = frame.shape[:2]
        ai_roi = frame[int(0.077 * h):int(0.107 * h), int(0.040 * w):int(0.200 * w)]
        if ai_roi.size == 0:
            return False, None
        ai_gray = cv2.cvtColor(ai_roi, cv2.COLOR_BGR2GRAY)
        if float(ai_gray.std()) < 15.0:
            return False, None
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        ai_enhanced = clahe.apply(ai_gray)
        _, ai_binary = cv2.threshold(ai_enhanced, 100, 255, cv2.THRESH_BINARY)
        text_area = (ai_binary == 0).sum() / ai_binary.size
        if 0.03 < text_area < 0.95:
            return True, "agent_info_text"
        return False, None
    except Exception:
        return False, None


def _verify_s18(frame: np.ndarray) -> tuple[bool, str | None]:
    """
    S18: verificar por múltiples indicadores visuales (cualquiera basta):
    1. Subrayado amarillo del tab 'Atributos base'
    2. Grilla de stats (4+ líneas separadoras horizontales)
    3. Zona de valores numéricos brillantes en columna derecha
    4. "AGENT INFO" — texto sutil sobre el nombre de facción (exclusivo S18)

    Esta función corre como confirmación post-template-match en `ScreenDetector._verify()`.
    Para detección INDEPENDIENTE de templates (usada como fallback en monitor cuando
    classify() devuelve S12) ver `_deep_detect_s18()`.
    """
    reasons: list[str] = []
    for indicator in (
        _s18_visual_tab_amarillo,
        _s18_visual_grilla_stats,
        _s18_visual_valores_brillantes,
        _s18_visual_agent_info_clahe,
    ):
        ok, reason = indicator(frame)
        if ok and reason:
            reasons.append(reason)
    if reasons:
        return True, "+".join(reasons)
    return False, "sin_indicadores_s18"


# =========================================================================
# Deep S18 multi-trigger detector (resolución-agnóstico, usa OCR)
# =========================================================================

# Banner superior-izquierdo donde aparece "AGENT INFO" / "INFO AGENTE" / nombre facción.
# ROI más amplia que la visual CLAHE para dar margen al OCR.
_S18_OCR_BANNER_ROI = (0.030, 0.045, 0.230, 0.090)  # (x, y, w, h) normalizados

# Panel central donde caen los 11 stats con labels.
_S18_OCR_STATS_ROI = (0.150, 0.200, 0.700, 0.450)

# Grupos de keywords de stats (case-insensitive, sin acentos).
# Cada grupo cuenta como UNA aparición si cualquiera de sus términos
# está en el OCR del panel central. Score = grupos distintos detectados.
_S18_STAT_KEYWORD_GROUPS: list[list[str]] = [
    ["pv", "hp"],
    ["ataque", "atq", "atk"],
    ["defensa", "def"],
    ["impacto", "imp"],
    ["prob", "crit"],
    ["dano critico", "dano crit", "dmg crit"],
    ["tasa anomalia", "anomalia"],
    ["maestria"],
    ["perforacion", "pen"],
    ["recuperacion", "energia", "recup"],
]

# Palabras que indican AGENT INFO banner (variantes ES/EN).
_S18_AGENT_INFO_KEYWORDS: tuple[str, ...] = (
    "agent info",
    "agent",
    "info agente",
    "perfil agente",
    "atributos base",
)


def _strip_accents_lower(text: str) -> str:
    """Normaliza texto: minúsculas + remueve acentos comunes ES."""
    if not text:
        return ""
    repl = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ñ": "n",
    }
    out = text.lower()
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def _ocr_crop(frame: np.ndarray, ocr, roi: tuple[float, float, float, float], psm: int = 6) -> str:
    """OCR de una ROI normalizada. Devuelve string vacío si falla."""
    if frame is None or frame.size == 0 or ocr is None:
        return ""
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = roi
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return ""
        text, _conf = ocr.text(crop, psm=psm, lang="spa")
        return text or ""
    except Exception:
        return ""


def _s18_ocr_agent_info(frame: np.ndarray, ocr) -> tuple[bool, str | None]:
    """Indicador OCR (peso 2): banner 'AGENT INFO' / 'INFO AGENTE' / 'Atributos base'."""
    raw = _ocr_crop(frame, ocr, _S18_OCR_BANNER_ROI, psm=7)
    norm = _strip_accents_lower(raw)
    for kw in _S18_AGENT_INFO_KEYWORDS:
        if kw in norm:
            return True, f"ocr_agent_info({kw})"
    return False, None


def _s18_ocr_stat_keywords(frame: np.ndarray, ocr) -> tuple[int, str | None]:
    """
    Indicador OCR (peso 2 si >=3 grupos): keywords de stats en panel central.
    Devuelve (count_grupos_detectados, reason).
    """
    raw = _ocr_crop(frame, ocr, _S18_OCR_STATS_ROI, psm=6)
    norm = _strip_accents_lower(raw)
    if not norm:
        return 0, None
    hits = 0
    matched_groups: list[str] = []
    for group in _S18_STAT_KEYWORD_GROUPS:
        for kw in group:
            if kw in norm:
                hits += 1
                matched_groups.append(group[0])
                break
    if hits == 0:
        return 0, None
    return hits, f"ocr_stats_{hits}grp:{','.join(matched_groups[:5])}"


def _deep_detect_s18(frame: np.ndarray, ocr=None) -> "ScreenState | None":
    """
    Detector independiente de S18 (Perfil agente — Atributos base).

    Diseñado para correr como FALLBACK en `monitor._run()` cuando
    `ScreenDetector.classify()` devuelve S12 (templates no matchean a la
    resolución del usuario, etc.). A diferencia de `_verify_s18`, esta
    función no requiere un template match previo y agrega 2 indicadores
    OCR que son exclusivos de S18.

    Scoring (6 indicadores, max 9 puntos):
      Visuales peso 1 c/u:
        - tab_amarillo
        - grilla_stats
        - valores_brillantes
      Visual peso 2 (firma fuerte pero ruidosa en modales con texto):
        - agent_info_clahe  (texto sutil detectado por CLAHE+threshold)
      OCR peso 2 c/u (opcionales, solo si ocr está disponible):
        - ocr_agent_info  ("AGENT INFO" / "INFO AGENTE" / "Atributos base")
        - ocr_stats_kw    (≥3 grupos de keywords stats)

    Anti-FP — promoción a alta confianza requiere al menos 1 indicador OCR
    (ocr_score ≥ 2). Razón: el CLAHE + grilla disparan también en S16
    (Detalle set disco) que comparte layout con grilla y texto en banner
    superior. Sin OCR, los visuales no pueden distinguir S18 de otros
    modales con grilla. La señal textual "AGENT INFO" / "Atributos base"
    sí es exclusiva.

    Decisión:
      ocr_score ≥ 2 AND total ≥ 3 → S18 conf 0.75 method="deep_detect"
      total ≥ 2                    → S18 conf 0.55 method="deep_detect_tentativo"
      total < 2                    → None

    Calibración (QA sobre 7 fixtures 2559×1439 + 5 FPs):
      - S18 fixtures, sin OCR: 7/7 disparan CLAHE → tentativo conf 0.55
      - S18 fixtures, con OCR: 7/7 deberían llegar a deep_detect (conf 0.75)
      - FP modales, sin OCR: pueden dar tentativo (filtrados por buffer 2/3)
      - FP modales, con OCR no-S18: máximo tentativo (no promueven)

    Path tentativo: el monitor enruta el state al `TemporalBuffer.add()`
    normal (2/3 votos), no a `promote_now()`. Latencia ~300 ms adicional
    pero respeta el anti-FP por mayoría de frames.
    """
    if frame is None or frame.size == 0:
        return None

    visual_score = 0
    ocr_score = 0
    reasons: list[str] = []

    # Visuales peso 1
    for indicator in (
        _s18_visual_tab_amarillo,
        _s18_visual_grilla_stats,
        _s18_visual_valores_brillantes,
    ):
        ok, reason = indicator(frame)
        if ok and reason:
            visual_score += 1
            reasons.append(reason)

    # Visual peso 2 (CLAHE — firma fuerte pero comparte con modales con texto)
    ok, reason = _s18_visual_agent_info_clahe(frame)
    if ok and reason:
        visual_score += 2
        reasons.append(reason)

    # Indicadores OCR (peso 2 c/u). Cualquier excepción se ignora silenciosamente
    # para no romper la pipeline si Tesseract está mal configurado.
    if ocr is not None:
        try:
            ok, reason = _s18_ocr_agent_info(frame, ocr)
            if ok and reason:
                ocr_score += 2
                reasons.append(reason)
        except Exception:
            pass
        try:
            hits, reason = _s18_ocr_stat_keywords(frame, ocr)
            if hits >= 3 and reason:
                ocr_score += 2
                reasons.append(reason)
        except Exception:
            pass

    total = visual_score + ocr_score

    # Promoción a S18 SOLO con señal OCR confirmatoria de stats/banner.
    # El path "tentativo" (conf 0.55, visual-solo) fue ELIMINADO el 2026-06-03:
    # disparaba S18 falso sobre la pantalla de entrada (TV) y sobre S8 (la grilla
    # de efectos de set + el pill lima activaban CLAHE/valores_brillantes sin un
    # solo stat real). Los visuales NO distinguen S18 de otras pantallas con
    # grilla/texto; solo el OCR de "AGENT INFO"/keywords de stats es exclusivo.
    # La desambiguación S8↔S18 ahora la hace `detect_active_tab` (tab-bar).
    # Ver Documentacion/Dev_IA/2026-06-03_*.md §2.
    if ocr_score >= 2 and total >= 3:
        return ScreenState(
            code="S18",
            confidence=0.75,
            template_name="deep_detect:" + "+".join(reasons),
            verification=f"vis={visual_score} ocr={ocr_score}",
            method="deep_detect",
        )
    return None


def _verify_s22(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S22 sea el modal de recompensas del farmeo por baterías.

    "Obtenido" es un título GENÉRICO en ZZZ (correo, login, pase de batalla…), así que el
    template solo sería un FP a la espera. La firma real del modal es su grilla de recompensas:
    las FRANJAS DE RAREZA de los tiles. Los 4 fixtures dan 12-13; una pantalla sin grilla no
    llega a `_EXTRACCION_STRIP_MIN`. Mismo criterio que `_verify_s2`. Sin OCR (RNF-06)."""
    try:
        from app.core.parser_extraccion import (
            _EXTRACCION_STRIP_MIN,
            count_rarity_strips_viewport,
        )
        n = count_rarity_strips_viewport(frame)
        return (n >= _EXTRACCION_STRIP_MIN, f"strips={n}")
    except Exception:
        return (True, None)   # convención del repo: ante excepción, no bloquear


def _verify_s27(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S27 sea el banner de sintonización: el riel de canales con uno realzado.

    La franja de botones ×1/×10 ya es bastante específica, pero el riel es la firma que ninguna
    otra pantalla tiene: 6 pastillas en posiciones fijas, exactamente una con marco amarillo.
    Los 6 banners de 3.1 dan realce 0.036–0.076 contra ≤0.005 de las pastillas no seleccionadas.
    Sin OCR (RNF-06)."""
    try:
        from app.core.parser_gacha_banner import selected_channel
        sel = selected_channel(frame)
        return (sel is not None, f"canal={sel.idx}" if sel else "sin_realce")
    except Exception:
        return (True, None)


# Mínimo de badges de rareza para aceptar la grilla de S28. Medido sobre los fixtures: una
# grilla real da SIEMPRE 10; la animación de recolección (los televisores azules con las letras
# A/B) cae en la misma geometría y llega a 6; el splash del agente contratado da 1. El umbral va
# en el medio del hueco 6↔10, con margen para que un badge ilegible en captura viva no lo tumbe.
_S28_BADGE_MIN = 9


def _verify_s28(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S28 sea la grilla de resultados y no la animación que la precede.

    El título matchea altísimo (≥0.992), pero durante la animación el título ya está en pantalla
    con la grilla todavía sin revelar. Lo que separa las dos es la grilla en sí: 10 badges de
    rareza en posiciones fijas. Mismo criterio que `_verify_s2` y `_verify_s22`. Sin OCR."""
    try:
        from app.core.parser_gacha_result import count_rarity_badges
        n = count_rarity_badges(frame)
        return (n >= _S28_BADGE_MIN, f"badges={n}")
    except Exception:
        return (True, None)


# Banda del texto del diálogo de sustitución ("{PJ} equipa actualmente {set} ({slot}). ¿Deseas
# sustituirlo?") — 1 o 2 líneas, centrado. Generosa para cubrir ambos casos (medido sobre los 7
# fixtures). La usan `_verify_s23` (anti-FP) y el parser (parser_sustitucion).
_S23_TEXT_ROI = (0.10, 0.44, 0.80, 0.12)   # x, y, w, h
_RE_S23_VERIFY = re.compile(r"sustituir|equipa\s+actualmente", re.I)

# El sufijo de SLOT es lo único que separa el diálogo de disco del de ARMA: un disco vive en un
# slot 1-6 y el juego lo imprime, un W-Engine no tiene slot.
#     disco → "Yixuan equipa actualmente Balada de la rama y la espada (2). ¿Deseas sustituirlo?"
#     arma  → "Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?"
# Medido con Tesseract sobre los 7 fixtures de disco y los 4 de arma: 7/7 con sufijo, 4/4 sin.
# El patrón replica el de `parser_sustitucion` a propósito —incluidos el "(" opcional (el OCR se
# lo come a veces) y los alias de dígito de la variante laxa—, porque el criterio de ruteo tiene
# que ser el MISMO que el de parseo: si el parser va a poder leer un slot de ahí, es un disco.
_RE_S23_SLOT = re.compile(r"\(?\s*[1-6]\s*\)|\(\s*[il|¡zsb]\s*\)", re.I)
_s23_verify_ocr = None


def _get_dialog_verify_ocr():
    """Tesseract lazy para los verifies de diálogo (`_verify_s23`, `_verify_s25`). Corre solo
    cuando el template de botones matchea (hay un diálogo en pantalla), así que el costo es
    puntual. None si falta.

    Lo comparten dos estados porque la fila "Cancelar/Confirmar" es genérica de ZZZ: el template
    dice "hay un diálogo", y el TEXTO dice cuál."""
    global _s23_verify_ocr
    if _s23_verify_ocr is None:
        try:
            from app.core.ocr_tesseract import TesseractBackend
            _s23_verify_ocr = TesseractBackend()
        except Exception:
            _s23_verify_ocr = False   # sentinela: no reintentar
    return _s23_verify_ocr or None


def _verify_s23(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S23 sea el diálogo de SUSTITUCIÓN de disco. El template es la fila
    "Cancelar/Confirmar", GENÉRICA de ZZZ (varios diálogos de confirmación la tienen), así que el
    template solo sería un FP a la espera. La firma exclusiva es el TEXTO del diálogo ("... equipa
    actualmente ... sustituirlo") **más el sufijo de slot**, que es lo que lo separa del diálogo
    gemelo de W-Engine (S29). OCR de esa banda (anti-FP, RNF-02). Sin Tesseract → no bloquear
    (convención del repo: ante ausencia/excepción, no degradar).

    Exigir el slot NO abre un modo de fallo nuevo: un frame de disco cuyo "(N)" el OCR arruine
    hoy ya cae en S23, el parser se abstiene y el swap no ocurre (solo deja un PNG en
    `audit/s23_parse_fallo/`). Con este cambio ese mismo frame cae en S29 y el swap tampoco
    ocurre. Cambia la etiqueta, no el desenlace."""
    ocr = _get_dialog_verify_ocr()
    if ocr is None:
        return (True, None)
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _S23_TEXT_ROI
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return (True, None)
        text, _ = ocr.text(crop, psm=6, lang="spa")
        text = text or ""
        if not _RE_S23_VERIFY.search(text):
            return (False, "txt=no-match")
        if not _RE_S23_SLOT.search(text):
            return (False, "txt=sin-slot")   # es el diálogo, pero de un arma → S29
        return (True, "txt=sustituir")
    except Exception:
        return (True, None)


def _verify_s29(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S29 sea el diálogo de sustitución de un **W-Engine**: el mismo texto de S23
    pero SIN sufijo de slot (un arma no vive en un slot).

    **Falla cerrado**, con el mismo razonamiento que `_verify_s25`: sin OCR no hay forma de
    separarlo de S23, y de los dos el que tiene consecuencias es S23 —mueve un disco entre PJs y
    **escribe la DB**. En una máquina sin Tesseract, S29 sencillamente no existe y S23 queda
    exactamente como estaba (RNF-01/02: ante la duda gana el que hace algo)."""
    ocr = _get_dialog_verify_ocr()
    if ocr is None:
        return (False, "sin-ocr")
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _S23_TEXT_ROI      # misma banda: es el mismo diálogo genérico
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return (False, "roi-vacio")
        text, _ = ocr.text(crop, psm=6, lang="spa")
        text = text or ""
        if not _RE_S23_VERIFY.search(text):
            return (False, "txt=no-match")
        if _RE_S23_SLOT.search(text):
            return (False, "txt=con-slot")   # tiene slot → es un disco, es de S23
        return (True, "txt=arma-sin-slot")
    except Exception:
        return (False, "excepcion")


# El diálogo de confirmación del DESMONTAJE comparte con S23 la fila "Cancelar/Confirmar" (mismo
# template, 0.996-0.998), así que lo único que los separa es el texto:
#   S23 → "... equipa actualmente ... ¿Deseas sustituirlo?"
#   S25 → "... pistas de grado S. ¿Seguro que quieres desmontarlas?"
# "desmontar" cubre la conjugación que use el juego (desmontarla/desmontarlas/desmontarlos).
_RE_S25_VERIFY = re.compile(r"desmontar|desmontaje", re.I)


def _verify_s25(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S25 sea el diálogo de confirmación del DESMONTAJE.

    **Falla cerrado a propósito** — al revés que `_verify_s23`, que ante ausencia de OCR deja
    pasar. La convención del repo (no degradar ante ausencia) asume que el estado es el único
    que reclama esa pantalla; acá no lo es. Sin OCR no hay forma de distinguir este diálogo del
    de sustitución, y de los dos el que tiene consecuencias reales es S23: mueve un disco entre
    PJs y **escribe la DB**. S25 solo congela un contador. Ante la duda, gana el que hace algo
    (RNF-01/02: la decisión conservadora). En una máquina sin Tesseract S25 no existe y S23 queda
    exactamente como estaba."""
    ocr = _get_dialog_verify_ocr()
    if ocr is None:
        return (False, "sin-ocr")
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _S23_TEXT_ROI      # misma banda de texto: es el mismo diálogo genérico
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return (False, "roi-vacio")
        text, _ = ocr.text(crop, psm=6, lang="spa")
        ok = bool(_RE_S25_VERIFY.search(text or ""))
        return (ok, "txt=desmontar" if ok else "txt=no-match")
    except Exception:
        return (False, "excepcion")


# --- S26: detalle de W-Engine, que comparte template con el detalle de disco ------------------
# La pantalla del arma y la del disco son la MISMA salvo por el contenido del panel central:
# las dos matchean `s17_personalizacion_pistas.png` a 1.000. Se midieron y descartaron todos los
# discriminantes baratos:
#   · la fila de 5 estrellas (exclusiva del arma) NO sirve: un arma P1 tiene 1 estrella blanca y
#     4 grises, así que el llenado de esa banda ES la señal de refinamiento, no una constante.
#     Separación medida 0.58×, solapada.
#   · `_detect_s17_slot_by_hexagon` da None también para los 30 frames de disco de
#     `14_Slots_equipamiento`.
#   · `read_s17_action_button` devuelve 'reemplazar'/'desequipar' en las dos.
# Lo único que separa es el texto del panel (40/40 armas, 0/42 discos, con Paddle y con
# Tesseract):
#     disco → "Atributos secundarios" · "Efecto de conjunto"
#     arma  → "Atributos avanzados"   · "Efecto de amplificador"
_S26_PANEL_ROI = (0.31, 0.29, 0.20, 0.12)   # x, y, w, h — banda del panel con el header
_RE_S26_VERIFY = re.compile(r"avanzados|amplificador", re.I)

# Pre-gate de UNA SOLA DIRECCIÓN sobre la fila de estrellas. No sirve para afirmar "es un arma"
# (el llenado varía con el refinamiento: un P1 tiene 1 estrella blanca de 5), pero sí para
# descartar barato la mayoría de los discos y ahorrarles el OCR. Medido sobre 40 armas + 42
# discos, la distribución del disco es casi binaria:
#     armas   min 0.0229
#     discos  0.0000 (×32) · 0.0006 · 0.0609 (×10)
# Con el corte en 0.010 hay 2.3× de margen contra el arma más floja y 16× contra el grupo denso
# de discos, y **32/42 frames de disco evitan el OCR**. Importa porque este verify corre sobre
# TODA pantalla que matchee el template de S17, y sin el gate le agregaría ~334 ms por cambio de
# panel a un flujo de discos que hoy ya funciona.
#
# Si alguna vez fallara para un arma (variante sin fila de estrellas), el efecto es que esa
# pantalla vuelve a caer en S17 — el comportamiento previo a este hito, que es seguro.
_S26_STARS_BAND = (0.320, 0.212, 0.155, 0.040)
_S26_STARS_MIN = 0.010


def _s26_star_row_frac(frame: np.ndarray) -> float:
    """Fracción de blanco brillante en la banda de la fila de estrellas (~0.3 ms)."""
    h, w = frame.shape[:2]
    x, y, rw, rh = _S26_STARS_BAND
    roi = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    return float(((hsv[:, :, 2] > 200) & (hsv[:, :, 1] < 60)).mean())
_s26_verify_ocr = None
_s26_sig_cache: tuple[bytes, bool, str] | None = None


def _get_panel_verify_ocr():
    """OCR para el verify del panel. Prefiere Paddle y cae a Tesseract.

    NO reusa `_get_dialog_verify_ocr` (Tesseract) porque acá el costo importa: este verify corre
    sobre TODA pantalla que matchee el template de S17, discos incluidos. Medido sobre la banda:
    Paddle p50 124-235 ms contra Tesseract ~500 ms, y los dos aciertan 40/40 y 0/42. La banda
    angosta de una sola línea se probó y es peor en las dos dimensiones (25/40, mismo tiempo):
    el header no está a un `y` fijo porque los nombres largos envuelven y corren el panel.
    """
    global _s26_verify_ocr
    if _s26_verify_ocr is None:
        for mod, cls in (("app.core.ocr_paddle", "PaddleBackend"),
                         ("app.core.ocr_tesseract", "TesseractBackend")):
            try:
                _s26_verify_ocr = getattr(__import__(mod, fromlist=[cls]), cls)()
                break
            except Exception:
                continue
        else:
            _s26_verify_ocr = False
    return _s26_verify_ocr or None


# ROI de la FIRMA. Es la unión del ROI del OCR y de la banda de estrellas, no solo el primero:
# el veredicto depende de los dos (el pre-gate mira las estrellas), así que cachearlo bajo una
# firma que ignore la banda de estrellas dejaría el cache pudiendo devolver un veredicto que sus
# propias entradas ya no justifican.
_S26_SIG_ROI = (0.31, 0.20, 0.20, 0.21)


def _s26_panel_signature(frame: np.ndarray) -> bytes:
    """Firma barata (~0.3 ms) del panel: el ROI reducido a 24×12 en gris.

    El panel está QUIETO mientras el usuario lo mira, así que sin esto se pagaría un OCR por
    ciclo (cadencia 1000 ms ⇒ >12 % de duty cycle solo en verificar, contra el RNF-06 de < 3 %
    de CPU). Con la firma, el OCR corre una vez por CAMBIO de panel: medido, 0.31 ms con cache
    contra 168-334 ms sin él."""
    h, w = frame.shape[:2]
    x, y, rw, rh = _S26_SIG_ROI
    crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
    if crop.size == 0:
        return b""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return cv2.resize(gray, (24, 12), interpolation=cv2.INTER_AREA).tobytes()


def _verify_s26(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que la pantalla sea el detalle de un W-ENGINE y no el de un disco.

    **Falla cerrado**, igual que `_verify_s25` y por el mismo motivo invertido: sin OCR no hay
    forma de separar las dos pantallas, y de las dos la que tiene consecuencias es la de disco
    (S17 es donde se confirma el swap pendiente de S23, que escribe la DB). Sin OCR, S26 no
    dispara, el arma vuelve a caer en S17 y todo queda como antes de este hito — que era seguro,
    porque los parsers de disco se abstienen sobre frames de arma
    (`test_armas_no_contaminan_discos`).
    """
    global _s26_sig_cache
    try:
        sig = _s26_panel_signature(frame)
        if not sig:
            return (False, "roi-vacio")
        if _s26_sig_cache is not None and _s26_sig_cache[0] == sig:
            return (_s26_sig_cache[1], _s26_sig_cache[2])
        if _s26_star_row_frac(frame) < _S26_STARS_MIN:
            _s26_sig_cache = (sig, False, "sin-estrellas")
            return (False, "sin-estrellas")
        ocr = _get_panel_verify_ocr()
        if ocr is None:
            return (False, "sin-ocr")      # no se cachea: el OCR puede aparecer después
        h, w = frame.shape[:2]
        x, y, rw, rh = _S26_PANEL_ROI
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        text, _ = ocr.text(crop)
        ok = bool(_RE_S26_VERIFY.search(text or ""))
        motivo = "txt=avanzados" if ok else "txt=no-match"
        _s26_sig_cache = (sig, ok, motivo)
        return (ok, motivo)
    except Exception:
        return (False, "excepcion")


# Pill "Confirmar" CENTRADO del modal post-desmontaje. Es lo que lo distingue de los otros
# "Obtenido" y de los diálogos de dos botones: acá hay un único botón, centrado y más abajo.
# Medido sobre los fixtures: el modal post-desmontaje da 0.0222 de verde en este ROI, y TODOS
# los vecinos dan 0.0000 — el diálogo de confirmación del propio desmontaje (Ejemplo_8, que
# tiene Cancelar+Confirmar más arriba), los 4 de S22 y los 7 de S23.
_S24_CONFIRMAR_ROI = (0.40, 0.640, 0.20, 0.075)   # x, y, w, h
_S24_GREEN_LO = (35, 80, 80)
_S24_GREEN_HI = (85, 255, 255)
_S24_GREEN_MIN = 0.008                             # ~1/3 del objetivo, y el resto mide 0.0


def _verify_s24(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S24 sea el "Obtenido" que CONFIRMA un desmontaje.

    El título "Obtenido" es genérico en ZZZ — lo usan el correo, el login, el pase de batalla y
    sobre todo **S22** (drops del farmeo por baterías) — así que el template solo sería un FP a
    la espera. Dos condiciones independientes, ambas sin OCR (RNF-06):

    1. **Pill verde "Confirmar" centrado.** Este modal tiene un único botón; los diálogos de
       confirmación tienen dos (y más arriba), y S22 no tiene ninguno ahí.
    2. **Pocas franjas de rareza.** S22 exige ≥6 en su viewport y muestra 12-14; este modal
       muestra 2-3 iconos de material. Separa por estructura, no por texto.

    La 2ª es la que impide que los dos "Obtenido" se roben la pantalla: cada uno falla el verify
    del otro. Ante excepción no se bloquea (convención del repo)."""
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _S24_CONFIRMAR_ROI
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return (True, None)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green = float(cv2.inRange(hsv, _S24_GREEN_LO, _S24_GREEN_HI).mean()) / 255.0
        if green < _S24_GREEN_MIN:
            return (False, f"confirmar={green:.4f}")

        from app.core.parser_extraccion import (
            _EXTRACCION_STRIP_MIN,
            count_rarity_strips_viewport,
        )
        n = count_rarity_strips_viewport(frame)
        if n >= _EXTRACCION_STRIP_MIN:
            return (False, f"strips={n} (es S22)")
        return (True, f"confirmar={green:.4f} strips={n}")
    except Exception:
        return (True, None)


# --- S9: el inventario de DISCOS, que comparte chrome con el de AMPLIFICADORES ---------------
# Las dos pantallas son la misma grilla con el mismo panel de detalle a la derecha: el inventario
# de W-Engines matchea `s9_inventario_general.png` a **0.855-0.864** sobre los 6 fixtures, por
# encima del umbral 0.80 de S9 y sin ninguna verificación que lo frene. Hoy es inocuo porque el
# handler de S9 nunca se cableó; el día que se cablee, el pipeline de DISCOS estaría parseando
# armas. Es la misma trampa que S17/S26 y S23/S25, y se cierra igual: por el TÍTULO.
#     discos → "Pistas de disco [339/3000]"
#     armas  → "Amplificadores [57/2000]"
# El ancla del lado de las armas es la COLA `lificador`, no la palabra entera: sobre los 6
# fixtures el OCR nunca lee "Amplificadores" limpio y lo rompe de dos formas distintas —
# "Amoplificadores" (×4) y "Amolificadores" (×2)—, o sea que ni el arranque "Ampl" ni la "p"
# sobreviven. Lo que sí sobrevive en 6/6 es "lificadores".
_S9_HEADER_ROI = (0.02, 0.085, 0.35, 0.055)   # x, y, w, h — título arriba a la izquierda
_RE_S9_DISCOS = re.compile(r"pistas\s+de\s+disco", re.I)
_RE_S9_ARMAS = re.compile(r"lificador", re.I)


# Lectura del header cacheada **por invocación de `classify`**. No es un caché de módulo con
# invalidación ni un `lru_cache` sobre el frame: el ciclo de vida ES la invalidación, y lo
# gobierna `_lecturas_de_una_clasificacion()` abajo. Fuera de una clasificación vale `None` y la
# función lee siempre, como antes.
#
# Es un `ContextVar` y no un global para que dos hilos (monitor + UI) no compartan lectura.
_lectura_header: contextvars.ContextVar = contextvars.ContextVar("_lectura_header", default=None)


@contextmanager
def _lecturas_de_una_clasificacion():
    """Abre y CIERRA el caché de lecturas caras. Vive exactamente una invocación de `classify`.

    El `reset` va en un `finally`: si la clasificación revienta, el caché se cierra igual. Un
    caché que sobrevive a su invocación no se nota en los tiempos —sigue siendo rápido— se nota
    en los DATOS, contestando sobre el frame anterior."""
    token = _lectura_header.set({})
    try:
        yield
    finally:
        _lectura_header.reset(token)


def _read_inventory_header(frame: np.ndarray) -> str | None:
    """Texto del título del inventario, o None si no se pudo leer. Lo comparten `_verify_s9` y
    `_verify_s30`: el template dice "hay una grilla de inventario" y el título dice de QUÉ.

    En un `classify` de S9 los dos verifies corren (S30 primero, falla, después S9) y mandan al
    OCR **el mismo recorte byte a byte** — verificado por sha256, no por lectura del código. Eran
    ~330 ms pagados dos veces, la mitad del costo del ciclo S9 una vez arreglado el matcheo de
    templates (Dev_IA 2026-08-19).

    Lo que se cachea es la lectura CRUDA, no el veredicto: los dos verifies sacan conclusiones
    OPUESTAS del mismo texto (S30 exige ver "amplificador" y falla cerrado; S9 solo bloquea si lo
    ve, y ante basura deja pasar). Un caché del veredicto le daría a uno la respuesta del otro.
    """
    cache = _lectura_header.get()
    if cache is not None:
        guardado = cache.get("inventory_header")
        # Identidad del objeto, no del contenido: guardar el frame en la tupla lo mantiene vivo,
        # así que `is` no puede confundirse con otro que reusó su id.
        if guardado is not None and guardado[0] is frame:
            return guardado[1]

    ocr = _get_dialog_verify_ocr()
    if ocr is None:
        return None
    try:
        h, w = frame.shape[:2]
        x, y, rw, rh = _S9_HEADER_ROI
        crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
        if crop.size == 0:
            return None
        text, _ = ocr.text(crop, psm=7, lang="spa")
        text = text or ""
    except Exception:
        return None

    if cache is not None:
        cache["inventory_header"] = (frame, text)
    return text


def _verify_s9(frame: np.ndarray) -> tuple[bool, str | None]:
    """Rechaza S9 cuando la grilla es el inventario de AMPLIFICADORES y no el de discos.

    Solo bloquea cuando **ve positivamente** el título de armas. Si el OCR devuelve basura, deja
    pasar: hasta ahora S9 no tenía verificación ninguna, y este hito es un blindaje contra una
    pantalla concreta, no una recalibración de S9 (que además es NON_CAPTURE e informativo). Sin
    Tesseract → no bloquear, por la misma razón."""
    text = _read_inventory_header(frame)
    if text is None:
        return (True, None)
    if _RE_S9_ARMAS.search(text):
        return (False, "txt=amplificadores")
    if _RE_S9_DISCOS.search(text):
        return (True, "txt=pistas-de-disco")
    return (True, None)


def _verify_s30(frame: np.ndarray) -> tuple[bool, str | None]:
    """La contracara: S30 exige ver el título de AMPLIFICADORES.

    **Falla cerrado**, al revés que `_verify_s9`. Es la asimetría deliberada que hace que el par
    tenga un fallback definido: con el título ilegible el frame vuelve a S9 —el comportamiento de
    siempre— en vez de quedar en tierra de nadie. Y como S30 va ANTES en `_STATE_TEMPLATES`, el
    primer turno de verificación le toca al estricto (mismo mecanismo que S26 frente a S17)."""
    text = _read_inventory_header(frame)
    if text is None:
        return (False, "sin-ocr")
    if _RE_S9_ARMAS.search(text):
        return (True, "txt=amplificadores")
    return (False, "txt=no-match")


def _verify_s2(frame: np.ndarray) -> tuple[bool, str | None]:
    """Verifica que S2 sea un FARMEO DE DISCOS real. El template 's2_resultado_desafio' matchea
    (a ≥0.80) tanto los resultados de farmeo de discos como OTRAS pantallas de "Resultados del
    desafío" (recompensas no-disco: chips/monedas) por el mismo layout de título.
    La firma que distingue el farmeo de discos es la grilla de recompensas con FRANJAS DE RAREZA
    (gold/purple/blue) de los tiles de disco. Sin ≥`_DISC_STRIP_MIN` franjas ⇒ no es farmeo de
    discos ⇒ verificación FALLA (el pipeline degrada la confianza y cae a S12). Sin OCR (RNF-06)."""
    try:
        from app.core.parser_s2 import count_reward_rarity_strips, _DISC_STRIP_MIN
        n = count_reward_rarity_strips(frame)
        return (n >= _DISC_STRIP_MIN, f"disc_strips={n}")
    except Exception:
        return (True, None)   # error inesperado: no bloquear (conservador, consistente con _verify)


# ROI del gramófono/hexágono "DRIVER" del selector de tienda de música (S4). Ahí S4 muestra el
# control metálico OSCURO (baja saturación) mientras S15 (menú de personajes, mismo chrome "Plan
# de entrenamiento") muestra la grilla de retratos COLORIDOS de agentes. La fracción de píxeles
# coloridos separa limpio: S4 ≤0.014 vs S15 ≥0.184 (17 fixtures, QA 2026-07-09). Sin OCR (RNF-06).
_S4_GRAMOFONO_ROI = (0.63, 0.25, 0.88, 0.72)   # x0, y0, x1, y1
_S4_COLORFUL_MAX = 0.10                          # margen holgado (13× de separación)

# Contraste (desvío estándar en gris) del mismo ROI. Segunda señal, INDEPENDIENTE del color, y
# hace falta: el color solo NO alcanza.
#
# Regresión 2026-08-16 (`Menu_Personajes/Ejemplo_10.png`): el menú lista en GRIS a los personajes
# que no se poseen, así que una zona de la lista dominada por grises tiene colorido **0.048** —
# por debajo del umbral— y el menú se clasificaba como tienda de música. No es un caso de
# laboratorio: una pasada de censo recorre TODA la lista, así que cae ahí seguro.
#
# El contraste separa por ESTRUCTURA, no por paleta: la grilla tiene decenas de tiles con bordes
# duros y texto (alto std) los pinte como los pinte; el gramófono es un objeto oscuro y liso.
# Medido sobre 9 fixtures de cada uno: S4 ∈ [19.2, 22.1] · S15 ∈ [51.6, 85.7] (2.3× de
# separación; el 51.6 es justamente Ejemplo_10, el peor caso gris).
_S4_CONTRAST_MAX = 35.0


def _is_music_selector(frame: np.ndarray) -> bool:
    """True si el panel derecho es el gramófono oscuro del selector de tienda de música (S4),
    NO la grilla de retratos del menú de personajes (S15). Ambos comparten el chrome "Plan de
    entrenamiento" (el template de S15 eclipsa a S4, que no tiene template propio). Cheap, sin
    OCR (RNF-06).

    Pide **las dos** señales: poco color Y poco contraste. Exigir ambas solo vuelve más estricta
    la clasificación como S4, que es la dirección segura — un falso S4 manda el frame a handlers
    que no corresponden, mientras que fallar la detección deja el frame en S15, su default.
    Ver `_S4_CONTRAST_MAX` para por qué el color solo no alcanza.
    """
    try:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = _S4_GRAMOFONO_ROI
        crop = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if crop.size == 0:
            return False
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        colorful = float(((hsv[:, :, 1] > 60) & (hsv[:, :, 2] > 60)).mean())
        if colorful >= _S4_COLORFUL_MAX:
            return False
        contraste = float(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).std())
        return contraste < _S4_CONTRAST_MAX
    except Exception:
        return False


# Registry: {state_code: verify_func}
_VERIFICATION_REGISTRY: dict[str, callable] = {
    "S2":  _verify_s2,
    "S22": _verify_s22,
    "S23": _verify_s23,
    "S29": _verify_s29,
    "S24": _verify_s24,
    "S25": _verify_s25,
    "S9":  _verify_s9,
    "S30": _verify_s30,
    "S3":  _verify_s3,
    "S10": _verify_s10,
    "S17": _verify_s17,
    "S18": _verify_s18,
    "S26": _verify_s26,
    "S27": _verify_s27,
    "S28": _verify_s28,
}


# =========================================================================
# Funciones de slot detection (multi-método)
# =========================================================================

def _extract_slot_from_roi(
    frame: np.ndarray, ocr,
    roi: tuple[float, float, float, float]
) -> int | None:
    """Método A: OCR del título 'Set Name (N)'. Devuelve slot 1-6 o None."""
    if frame is None or frame.size == 0 or ocr is None:
        return None
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    crop = frame[int(y*h):int((y+rh)*h), int(x*w):int((x+rw)*w)]
    if crop.size == 0:
        return None
    try:
        text, _ = ocr.text(crop, psm=6, lang="spa")
    except Exception:
        return None
    if not text:
        return None
    m = _SLOT_RE.search(text)
    if not m:
        return None
    slot = int(m.group(1))
    return slot if 1 <= slot <= 6 else None


def _detect_slot_by_glow(frame: np.ndarray, ocr=None) -> int | None:
    """
    Método B: detectar slot seleccionado por el aro brillante (glow verde/amarillo).
    Independiente de OCR. Funciona incluso si Tesseract no lee el título.
    """
    if frame is None or frame.size == 0:
        return None
    h, w = frame.shape[:2]
    try:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    except Exception:
        return None
    glow_mask = cv2.inRange(hsv, _SLOT_GLOW_HSV_LOWER, _SLOT_GLOW_HSV_UPPER)

    best_slot = None
    best_glow = 0
    for slot, (nx, ny, nw, nh) in _SLOT_POSITIONS.items():
        x, y = int(nx * w), int(ny * h)
        rw, rh = int(nw * w), int(nh * h)
        roi_mask = glow_mask[y:y+rh, x:x+rw]
        if roi_mask.size == 0:
            continue
        glow_pixels = roi_mask.sum() / 255
        if glow_pixels > best_glow:
            best_glow = glow_pixels
            best_slot = slot

    # Umbral mínimo: al menos 50 píxeles glow para considerar válido
    if best_slot is not None and best_glow >= 50:
        return best_slot
    return None


def extract_s17_slot(frame: np.ndarray, ocr) -> int | None:
    """
    S17 slot detection multi-método:
    1. OCR del título (Método A) — si confianza implícita > 0
    2. Glow ring HSV (Método B) — fallback
    """
    slot = _extract_slot_from_roi(frame, ocr, _S17_TITLE_ROI)
    if slot is not None:
        return slot
    return _detect_slot_by_glow(frame, ocr)


def extract_s9_slot(frame: np.ndarray, ocr) -> int | None:
    """S9 slot detection via OCR del título en panel derecho."""
    return _extract_slot_from_roi(frame, ocr, _S9_TITLE_ROI)


# =========================================================================
# Templates definitions
# =========================================================================

_STATE_TEMPLATES: list[dict] = [
    {"code": "S16", "template": "s16_detalle_set_disco.png",        "desc": "Detalle set de discos (modal Información de conjunto)"},
    # S26 REUSA el template de S17: la pantalla del arma y la del disco son la misma salvo por el
    # panel, y matchean las dos a 1.000. Va ANTES que S17 a propósito — `passing.sort` es estable,
    # así que ante el empate el primer turno de verificación le toca al que aparece primero, y acá
    # el estricto es S26. Si S17 fuera primero, su verify genérico (Hough de líneas en el panel)
    # pasaría sobre un frame de arma y S26 no llegaría a probarse nunca.
    # (Es el mecanismo de S23/S25 con los roles invertidos: allá el primer turno es del que
    # escribe la DB; acá el que escribe la DB es el fallback, y el que se adelanta es el que se
    # niega a sí mismo cuando no está seguro.)
    {"code": "S26", "template": "s17_personalizacion_pistas.png",   "desc": "Equipamiento PJ vista detalle W-Engine"},
    {"code": "S17", "template": "s17_personalizacion_pistas.png",   "desc": "Equipamiento PJ vista detalle (Personalización pistas)"},
    {"code": "S18", "template": "s18a_perfil_agente_recomendacion.png", "desc": "Perfil agente Atributos base (recomendación equipo)"},
    {"code": "S18", "template": "s18b_perfil_agente_completo.png",      "desc": "Perfil agente Atributos base (equipamiento completo)"},
    {"code": "S18", "template": "s18c_perfil_agente_tab_atributos.png",  "desc": "Perfil agente — tab 'Atributos base' subrayado amarillo"},
    # Gacha ANTES que S2, a propósito: gana el primero cuya verificación pasa, y el template de
    # S2 (banda superior oscura) sobre-matchea pantallas oscuras. Medido 2026-07-29: el banner
    # `Aria.png` da 0.773 contra `s2_resultado_desafio` con umbral S2 = 0.80 — margen de 0.027
    # contra un estado que CAPTURA DISCOS. Con el gacha primero, un banner nunca llega a probar S2.
    {"code": "S28", "template": "s28_resultados_sintonizacion.png", "desc": "Resultados de sintonización (grilla del x10)"},
    {"code": "S27", "template": "s27_banner_sintonizacion.png",    "desc": "Canal de sintonización (banner)"},
    {"code": "S2",  "template": "s2_resultado_desafio.png",        "desc": "Resultado del Desafio"},
    {"code": "S2",  "template": "s2_resultado_desafio_evento.png", "desc": "Resultado del Desafio (evento doble recompensa x2)"},
    {"code": "S5",  "template": "s5_resultado_afinacion.png",       "desc": "Resultado de afinacion"},
    {"code": "S5",  "template": "s5_resultado_afinacion_header.png", "desc": "Resultado de afinacion (header, robusto a selección de disco)"},
    # S30 REUSA el template de S9 y va ANTES a propósito, por el mecanismo de S26/S17: ante
    # scores empatados el primer turno de verificación le toca al ESTRICTO. `_verify_s30` exige
    # ver "Amplificadores" y falla cerrado; `_verify_s9` deja pasar si el título es ilegible. Al
    # revés, S9 se comería todo frame con el título borroso y S30 no llegaría a probarse.
    {"code": "S30", "template": "s9_inventario_general.png",        "desc": "Inventario general de amplificadores (W-Engines)"},
    {"code": "S9",  "template": "s9_inventario_general.png",        "desc": "Inventario general de discos"},
    {"code": "S11", "template": "s11_desmontaje.png",               "desc": "Pantalla desmontaje"},
    {"code": "S10", "template": "s10_modal_upgrade.png",            "desc": "Modal upgrade"},
    {"code": "S20", "template": "s20_materiales_recuperados.png",   "desc": "Materiales recuperados (vuelto post-mejora)"},
    {"code": "S8",  "template": "s8_agente_driver.png",             "desc": "Equipamiento disco personaje (vista previa)"},
    {"code": "S3",  "template": "s3_modal_detalle_drop.png",        "desc": "Modal detalle drop (post-farmeo)"},
    {"code": "S6",  "template": "s6_tienda_detalle_panel.png",      "desc": "Tienda musica panel"},
    {"code": "S7",  "template": "s7_tienda_detalle_full.png",       "desc": "Tienda musica fullscreen"},
    {"code": "S7",  "template": "s7_detalle_full_iconos.png",       "desc": "Vista individual disco (cluster papelera/candado/R/T)"},
    {"code": "S13", "template": "s13_seleccion_set_farmeo.png",     "desc": "Selección set de discos a farmear"},
    {"code": "S14", "template": "s14_seleccion_equipo_combate.png", "desc": "Selección de equipo pre-combate"},
    {"code": "S15", "template": "s15_menu_personajes.png",          "desc": "Menú de personajes (plan entrenamiento)"},
    {"code": "S21", "template": "s21_seleccion_usos.png",           "desc": "Modal selección número de usos (baterías)"},
    {"code": "S22", "template": "s22_obtenido.png",                 "desc": "Modal 'Obtenido' (drops del farmeo por baterías)"},
    {"code": "S23", "template": "s23_sustitucion.png",              "desc": "Diálogo de sustitución de disco entre PJs (Cancelar/Confirmar)"},
    {"code": "S24", "template": "s24_obtenido_desmontaje.png",      "desc": "Modal 'Obtenido' (confirmación post-desmontaje)"},
    # S25 REUSA el template de S23 a propósito: la fila "Cancelar/Confirmar" es genérica de ZZZ y
    # matchea los dos diálogos por igual (0.996-0.998). Lo que los separa es el verify de texto.
    # Va DESPUÉS de S23 en la lista: ante scores empatados el orden decide quién se verifica
    # primero, y el primer turno le toca al estado que escribe la DB.
    {"code": "S25", "template": "s23_sustitucion.png",              "desc": "Diálogo de confirmación del desmontaje (grado S)"},
    # S29 (sustitución de W-Engine) reusa el mismo template por el mismo motivo, y va último por
    # el mismo criterio: los tres diálogos empatan en score y el primer turno es del que escribe
    # la DB. Los verifies de S23 y S29 son mutuamente excluyentes por construcción (con slot / sin
    # slot), así que el orden acá es cinturón además de tirantes.
    {"code": "S29", "template": "s23_sustitucion.png",              "desc": "Diálogo de sustitución de W-Engine entre PJs"},
]


def describe_state(code: str) -> str:
    """Devuelve descripción legible para un código de estado."""
    return STATE_DESCRIPTIONS.get(code, code)


# =========================================================================
# ScreenDetector — clasificador principal
# =========================================================================

class ScreenDetector:
    """
    Clasificador multi-capa de estado de pantalla.
    Capa 1: template matching con threshold dinámico por estado.
    Capa 2: verificación secundaria (elementos UI únicos).
    Capa 3: HSV fallback para pantallas con paleta única.
    """

    def __init__(
        self,
        templates_dir: Path = TEMPLATES_DIR,
        threshold: float = MATCH_THRESHOLD,
        use_state_machine: bool = True,
    ):
        self._default_threshold = threshold
        self._templates: list[dict] = []
        self._missing: list[str] = []
        self._state_machine = StateMachine() if use_state_machine else None
        self._last_raw_state: str | None = None

        for entry in _STATE_TEMPLATES:
            path = templates_dir / entry["template"]
            if path.exists():
                tmpl = cv2.imread(str(path))
                if tmpl is not None:
                    self._templates.append({
                        "code": entry["code"],
                        "name": entry["template"],
                        "img": tmpl,
                    })
                    continue
            self._missing.append(entry["template"])

    @property
    def missing_templates(self) -> list[str]:
        return list(self._missing)

    @property
    def loaded_count(self) -> int:
        return len(self._templates)

    def state_machine_reset(self) -> None:
        if self._state_machine:
            self._state_machine.reset()

    @property
    def prev_state_code(self) -> str | None:
        if self._state_machine:
            return self._state_machine.prev_code
        return None

    # ---- Capa 1: Template matching -----------------------------------------

    # -- Pase grueso: localizar barato, confirmar caro pero chico ------------

    @staticmethod
    def _gray_tmpl(entry: dict) -> np.ndarray:
        """Gris del template, cacheado en la propia entrada. Perezoso a propósito: varios tests
        reemplazan `_templates` en caliente con entradas recién armadas."""
        g = entry.get("gray")
        if g is None:
            img = entry["img"]
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
            entry["gray"] = g
        return g

    @classmethod
    def _small_tmpl(cls, entry: dict) -> "np.ndarray | None":
        """Template reducido para el pase grueso, o None si al achicarlo deja de discriminar."""
        if "small" not in entry:
            s = cv2.resize(cls._gray_tmpl(entry), None, fx=_COARSE_SCALE, fy=_COARSE_SCALE,
                           interpolation=cv2.INTER_AREA)
            entry["small"] = s if min(s.shape[:2]) >= _COARSE_MIN_TMPL else None
        return entry["small"]

    @staticmethod
    def _picos(mapa: np.ndarray, k: int, radio_y: int, radio_x: int) -> list[tuple[int, int]]:
        """Hasta `k` máximos locales del mapa de respuesta, con supresión de no-máximos.

        Devuelve posiciones (x, y). Muta `mapa` — el llamador no lo reusa."""
        picos: list[tuple[int, int]] = []
        for _ in range(k):
            _, val, _, loc = cv2.minMaxLoc(mapa)
            if val <= -1.0:
                break
            picos.append((int(loc[0]), int(loc[1])))
            x0, y0 = max(0, loc[0] - radio_x), max(0, loc[1] - radio_y)
            x1 = min(mapa.shape[1], loc[0] + radio_x + 1)
            y1 = min(mapa.shape[0], loc[1] + radio_y + 1)
            mapa[y0:y1, x0:x1] = -1.0
        return picos

    @staticmethod
    def _confirmar(gray_frame: np.ndarray, gray_tmpl: np.ndarray,
                   picos: list[tuple[int, int]]) -> float:
        """Score a RESOLUCIÓN COMPLETA, mirando solo un ROI alrededor de cada pico grueso.

        Es un máximo sobre un SUBCONJUNTO de las posiciones que barría el match global, así que
        **solo puede quedar por debajo, nunca por encima**: este camino no puede inventar un falso
        positivo. El riesgo posible es el contrario (perder un match real por mirar donde no es), y
        para eso están los `_COARSE_PEAKS`."""
        th, tw = gray_tmpl.shape[:2]
        H, W = gray_frame.shape[:2]
        mejor = 0.0
        for lx, ly in picos:
            cx, cy = int(lx / _COARSE_SCALE), int(ly / _COARSE_SCALE)
            x0, y0 = max(0, cx - _COARSE_PAD), max(0, cy - _COARSE_PAD)
            x1, y1 = min(W, cx + tw + _COARSE_PAD), min(H, cy + th + _COARSE_PAD)
            roi = gray_frame[y0:y1, x0:x1]
            if roi.shape[0] < th or roi.shape[1] < tw:
                continue
            val = float(cv2.minMaxLoc(cv2.matchTemplate(roi, gray_tmpl, cv2.TM_CCOEFF_NORMED))[1])
            if val > mejor:
                mejor = val
        return mejor

    def _scores_por_archivo(self, gray_frame: np.ndarray) -> dict[str, float]:
        """Confianza por ARCHIVO de template (no por estado: 31 entradas usan 27 archivos, y
        S23/S25/S29 comparten uno solo — matchearlo tres veces es calcular tres veces el mismo
        número).

        Un archivo queda FUERA del dict cuando no entra en el frame o cuando el pase grueso lo
        descartó; el llamador lo saltea igual que antes se salteaba un template más grande que el
        frame."""
        fh, fw = gray_frame.shape[:2]
        usar_grueso = (fh * fw) >= _COARSE_MIN_PIXELS
        small_frame = (cv2.resize(gray_frame, None, fx=_COARSE_SCALE, fy=_COARSE_SCALE,
                                  interpolation=cv2.INTER_AREA) if usar_grueso else None)

        # Umbral más PERMISIVO entre los estados que declaran cada archivo: el shortlist no puede
        # descartar por el umbral de S25 algo que a S23 le habría alcanzado.
        umbral: dict[str, float] = {}
        for entry in self._templates:
            thr = THRESHOLD_BY_STATE.get(entry["code"], self._default_threshold)
            n = entry["name"]
            umbral[n] = thr if n not in umbral else min(umbral[n], thr)

        scores: dict[str, float] = {}
        gruesos: dict[str, tuple[list[tuple[int, int]], float, np.ndarray]] = {}

        for entry in self._templates:
            n = entry["name"]
            if n in scores or n in gruesos:
                continue
            gray_tmpl = self._gray_tmpl(entry)
            th, tw = gray_tmpl.shape[:2]
            if th > fh or tw > fw:
                continue                      # no entra en el frame (invariante viejo)

            small_tmpl = self._small_tmpl(entry) if usar_grueso else None
            if small_tmpl is None or small_tmpl.shape[0] > small_frame.shape[0] \
                    or small_tmpl.shape[1] > small_frame.shape[1]:
                scores[n] = float(cv2.minMaxLoc(
                    cv2.matchTemplate(gray_frame, gray_tmpl, cv2.TM_CCOEFF_NORMED))[1])
                continue

            mapa = cv2.matchTemplate(small_frame, small_tmpl, cv2.TM_CCOEFF_NORMED)
            tope = float(cv2.minMaxLoc(mapa)[1])
            picos = self._picos(mapa, _COARSE_PEAKS,
                                max(1, small_tmpl.shape[0] // 2), max(1, small_tmpl.shape[1] // 2))
            gruesos[n] = (picos, tope, gray_tmpl)

        # A confirmar: los que el pase grueso deja cerca de su umbral, MÁS los mejores en bruto —
        # estos últimos no van a pasar ningún umbral, pero sostienen el diagnóstico de S12.
        a_confirmar = {n for n, (_, tope, _) in gruesos.items() if tope >= umbral[n] - _COARSE_MARGIN}
        a_confirmar |= {n for n, _ in sorted(gruesos.items(), key=lambda kv: -kv[1][1])[:_COARSE_DIAG_TOP]}

        for n in a_confirmar:
            picos, _, gray_tmpl = gruesos[n]
            scores[n] = self._confirmar(gray_frame, gray_tmpl, picos)

        return scores

    def _template_candidates(self, frame: np.ndarray) -> tuple[list[ScreenState], ScreenState]:
        """Template matching con threshold dinámico por estado. Devuelve
        `(candidatos, s12_diag)`:
          - `candidatos`: TODOS los estados cuyo match supera su propio umbral, ordenados
            desc por confianza. Devolver la lista completa (no solo el mejor) permite al
            pipeline hacer FALLBACK: si el candidato top falla su verificación secundaria,
            probar el siguiente en vez de caer a S12. Esto evita que un match ESPURIO alto
            (p.ej. el template de S2 matchea la pantalla S13 a ~0.90 por chrome común)
            eclipse al match legítimo más bajo (S13) y produzca un parpadeo S13↔S12.
          - `s12_diag`: estado S12 con la confianza del mejor match global (diagnóstico
            cuando ningún template supera su umbral). **Ojo: no es cosmético** — `monitor` lo usa
            para decidir si un frame no-detalle resetea la identidad latcheada (umbral 0.50).

        El scoring lo hace `_scores_por_archivo`: un pase grueso a 1/4 que LOCALIZA y una
        confirmación a resolución COMPLETA dentro de un ROI chico. Las confianzas que salen de acá
        son las mismas que salían del match global —por eso `THRESHOLD_BY_STATE` no se tocó—, con
        una sola diferencia acotada: pueden quedar por debajo, nunca por encima. Ver Dev_IA
        2026-08-19 y `app/tests/unit/test_detector_template_pipeline.py`.
        """
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        fh, fw = gray_frame.shape[:2]

        scores = self._scores_por_archivo(gray_frame)

        overall_best_conf = 0.0
        overall_best_name = ""
        passing: list[ScreenState] = []

        for entry in self._templates:
            max_val = scores.get(entry["name"])
            if max_val is None:
                continue          # no entra en el frame, o el pase grueso lo descartó

            if max_val > overall_best_conf:
                overall_best_conf = max_val
                overall_best_name = entry["name"]

            state_threshold = THRESHOLD_BY_STATE.get(entry["code"], self._default_threshold)
            if max_val >= state_threshold:
                passing.append(ScreenState(entry["code"], round(max_val, 3), entry["name"], method="template"))

        passing.sort(key=lambda s: s.confidence, reverse=True)
        s12_diag = ScreenState("S12", round(overall_best_conf, 3), overall_best_name or "", method="template")
        return passing, s12_diag

    def _template_match(self, frame: np.ndarray) -> ScreenState:
        """Compat: el mejor candidato que supera su umbral, o S12 diagnóstico. Sin fallback
        de verificación (para eso usar `_template_candidates` + `_verify` en el pipeline)."""
        passing, s12_diag = self._template_candidates(frame)
        return passing[0] if passing else s12_diag

    # ---- Capa 2: Verificación secundaria ------------------------------------

    def _verify(self, state: ScreenState, frame: np.ndarray) -> ScreenState:
        """
        Verificación secundaria: confirma el estado chequeando elementos UI
        adicionales (no solo el template match).
        Si la verificación falla, degrada la confianza.
        """
        if state.code == "S12":
            return state

        verify_fn = _VERIFICATION_REGISTRY.get(state.code)
        if verify_fn is None:
            return state

        try:
            ok, detail = verify_fn(frame)
            state.verification = detail
            if not ok:
                # Degradar confianza y loguear
                state.confidence = round(state.confidence * 0.7, 3)
                if state.confidence < THRESHOLD_BY_STATE.get(state.code, self._default_threshold):
                    state.code = "S12"
                    state.template_name = f"verification_failed:{detail}"
        except Exception:
            pass

        return state

    # ---- Capa 3: HSV classifier --------------------------------------------

    def _classify_by_hsv(self, frame: np.ndarray) -> ScreenState | None:
        """
        HSV fallback: detecta pantallas con paleta de color única.
        Útil cuando templates fallan por resolución/escalado.
        """
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, w = frame.shape[:2]

            # (REMOVIDO 2026-07) Rama HSV S10 "hsv_green_bar": barra EXP verde en zona central-
            # inferior → S10 0.60. El green_ratio NO separa: Menu_Pausa (FP) mide 0.377, dentro
            # del rango de S10 real (0.0–0.503; varias S10 reales dan 0.0). Heurística FP-prone y
            # poco confiable → se elimina. S10 real se detecta por template s10_modal_upgrade +
            # `_verify_s10`. Ver QA negativo masivo.

            # S11: header rojo (zona superior central)
            header_roi = hsv[int(0.02*h):int(0.08*h), int(0.10*w):int(0.90*w)]
            if header_roi.size > 0:
                red_mask = cv2.inRange(header_roi, np.array([0, 80, 80]), np.array([10, 255, 255]))
                red_mask2 = cv2.inRange(header_roi, np.array([170, 80, 80]), np.array([180, 255, 255]))
                red_ratio = (red_mask.sum() + red_mask2.sum()) / header_roi.size / 255
                if red_ratio > 0.10:
                    return ScreenState("S11", 0.55, "hsv_red_header", method="hsv")

            # (REMOVIDO 2026-07) Rama HSV S18 "hsv_stats_grid": detectaba 4+ líneas
            # horizontales en el panel central → S18 0.55. Era un fallback demasiado genérico
            # (cualquier menú con listas/separadores horizontales lo disparaba: Guia_Rapida,
            # etc. → FP de S18). S18 real ya se cubre por template (s18a/b/c) + tab-override
            # (detect_active_tab) + `_deep_detect_s18` (OCR, monitor). Ver QA negativo masivo.

            return None
        except Exception:
            return None

    # ---- Pipeline completo --------------------------------------------------

    @staticmethod
    def _is_dark_frame(frame: np.ndarray, threshold: int = 35, dark_ratio: float = 0.68) -> bool:
        """
        Filtro de frame oscuro: si más del `dark_ratio`% de píxeles están
        por debajo de `threshold` de brillo, es una pantalla de carga/
        transición/diálogo que no tiene discos. Previene FPs en transiciones.

        Solo analiza el 60% central del ancho (x=0.20 a x=0.80) para evitar
        que personajes con fondo oscuro en los bordes disparen el filtro.

        Calibración del umbral (2026-06-06, medido sobre capturas reales):
          - S18 (Atributos base) LEGÍTIMOS: dark_ratio 0.513–0.595.
          - Zhu Yuan S18 (traje azul marino + fondo CRIT oscuro): 0.610 (medido).
          - Frames oscuros reales (loading/transición/FPs): 0.760–0.780.
        El umbral viejo (0.60) estaba clavado al techo de lo legítimo (sin
        margen): Zhu Yuan, a 0.610, lo cruzaba por 0.010 y parpadeaba S18↔S12
        (un frame con animación de fondo bajaba a 0.599 → S18 conf 0.98; el
        siguiente subía a 0.601 → S12), nunca extraía stats. Se sube a 0.68
        (medio del hueco 0.610↔0.760): ~0.07 de margen sobre Zhu Yuan y ~0.08
        bajo el frame oscuro real más claro. Una S18 real además matchea su
        template (~0.98), evidencia de que es legible.
        """
        if frame is None or frame.size == 0:
            return True
        h, w = frame.shape[:2]
        # Solo región central donde aparece UI
        center = frame[:, int(0.20*w):int(0.80*w)]
        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY) if center.ndim == 3 else center
        dark = (gray < threshold).sum()
        return (dark / gray.size) > dark_ratio

    @measure_latency("detector")
    def classify(self, frame: np.ndarray) -> ScreenState:
        """
        Instrumentado (QA-06 §3.1, presupuesto 50 ms) — solo mide con `DANIBOD_METRICS=1`.

        Envoltorio delgado: lo único que agrega es ABRIR y CERRAR el caché de lecturas caras
        (`_lecturas_de_una_clasificacion`). El ciclo de vida del caché es, literalmente, este
        `with` — por eso no hace falta invalidarlo ni versionarlo.
        """
        with _lecturas_de_una_clasificacion():
            return self._clasificar(frame)

    def _clasificar(self, frame: np.ndarray) -> ScreenState:
        """
        Pipeline completo de clasificación multi-capa:
        0. Dark frame filter (pantallas de carga/transición → S12 inmediato)
        1. Template matching (pase grueso que localiza + confirmación full-res en ROI)
        2. Verificación secundaria
        2.5 Override por tab-bar (ancla determinista de la familia detalle-PJ)
        3. State machine (transiciones válidas)
        4. HSV fallback solo si template no matchó
        """
        if frame is None or frame.size == 0:
            return ScreenState("S12", 0.0, "")

        # Capa 1+2: template matching con verificación secundaria y FALLBACK. Se prueban los
        # candidatos que superan su umbral, de mayor a menor confianza; el primero que
        # SOBREVIVE su verificación gana. Si el top falla (p.ej. S2 sobre una S13: matchea
        # ~0.90 pero `_verify_s2` no halla franjas de disco), se cae al siguiente candidato
        # (S13) en vez de a S12 — evita el parpadeo S13↔S12 por eclipse de un match espurio.
        passing, s12_diag = self._template_candidates(frame)
        state = None
        first_verified: "ScreenState | None" = None
        for cand in passing:
            verified = self._verify(cand, frame)
            if first_verified is None:
                first_verified = verified          # preserva el detalle verification_failed
            if verified.code != "S12":
                state = verified
                break
        if state is None:
            state = first_verified if first_verified is not None else s12_diag

        # Capa 0 (template-aware): filtro de frame oscuro SOLO si ningún template
        # matchó. Un match fuerte (p.ej. S17 a 1.00) evidencia contenido legible y
        # NO debe filtrarse aunque el fondo del elemento del PJ sea oscuro. Las
        # pantallas de carga/transición reales no matchean ningún template → S12.
        # (Regresión 2026-06-08: las S17 de PJs con fondo oscuro — Burnice/Caesar,
        # dark-ratio 0.68-0.70 — se filtraban como dark → S12 y no se capturaba
        # nada, mientras Yixuan 0.63 pasaba. Antes el filtro corría ANTES del
        # template y cortaba a ciegas; las FP reales — Detalle_set_disco 0.76 —
        # matchean su propio template, S16, así que no necesitan este atajo.)
        if state.code == "S12" and self._is_dark_frame(frame):
            return ScreenState("S12", 0.0, "dark_frame_filter")

        # Capa 2.5: override por tab-bar. Si hay un pill de pestaña activo, ES
        # autoritativo para distinguir S8/S18/S19 (familia detalle de agente),
        # por encima de template/HSV/deep-detect. Mata el FP histórico S18-sobre-S8
        # y el FP S10-sobre-S8 (cf. Dev_IA 2026-06-03). No corre OCR (~1 ms).
        tab_state = detect_active_tab(frame)
        # Corroboración anti-FP: el tab-bar solo es autoritativo si TAMBIÉN hay fila de avatares
        # resaltada (ambos coexisten en la familia detalle-agente). Sin ella, un pill amarillo
        # suelto en la franja inferior — p.ej. un tile de tienda amarillo del mapa de viaje
        # rápido — NO es la pantalla de agente (QA 2026-07-09: Viaje_rapido_1 → S18 falso 0.90).
        if tab_state is not None and selected_avatar_x(frame) is None:
            tab_state = None
        if tab_state is not None and tab_state != state.code:
            state = ScreenState(tab_state, 0.90, f"tab:{tab_state}", method="tab")
        elif tab_state is not None:
            state.method = "template+tab"  # template y tab coinciden → confianza extra

        # Capa 2.6: promoción S4 (selector tienda música). S4 comparte el chrome "Plan de
        # entrenamiento" con S15 (menú PJ) y NO tiene template propio → el template de S15 lo
        # eclipsa (0.96). Se confirma por AUSENCIA de la grilla de retratos coloridos en el ROI
        # del gramófono (QA 2026-07-09: S4 colorful≤0.014 vs S15≥0.184). Gate estricto a S15 para
        # no misfire sobre otras pantallas oscuras (solo S15 matchea el chrome compartido).
        if state.code == "S15" and _is_music_selector(frame):
            state = ScreenState("S4", 0.90, "music_selector_override", method="override")

        # Capa 3: HSV fallback si template no matchó (y el tab tampoco resolvió)
        if state.code == "S12":
            hsv_state = self._classify_by_hsv(frame)
            if hsv_state is not None:
                state = hsv_state

        # State machine: validar transición
        if self._state_machine is not None and state.code != "S12":
            validated = self._state_machine.validate(state.code)
            if validated != state.code:
                state.code = validated
                state.template_name = f"transition_filtered:{state.code}->{validated}"
                state.confidence = round(state.confidence * 0.5, 3)

        self._last_raw_state = state.code
        return state

    def classify_batch(self, frames: list[np.ndarray]) -> list[ScreenState]:
        return [self.classify(f) for f in frames]


# =========================================================================
# Polling cadence
# =========================================================================

def polling_cadence_ms(state: ScreenState) -> int:
    """
    Devuelve el intervalo de polling en ms según el estado actual (RF-04 §5).

    **Ojo: es un PERÍODO MÍNIMO, no una pausa agregada.** Medido el 2026-08-18 en S9: el ciclo
    real dura ~4,05 s porque el procesamiento (OCR) tarda más que la cadencia, así que el sleep ya
    era CERO. Bajarla de 1500 a 700 ms dio exactamente los mismos 16 ciclos por 65 s. Para acelerar
    S9 hay que atacar el procesamiento, no este número.
    """
    cadence = {
        "S1":  4000, "S2":  1000, "S3":   500, "S4":  4000,
        "S5":  1000, "S6":   500, "S7":   500, "S8":  1500,
        "S9":  1500, "S10":  500, "S12": 2000,
        "S13": 1000, "S14": 1000, "S15": 1000, "S16": 1500,
        "S17": 1000, "S18": 1500, "S19": 1500, "S21": 1000, "S22": 700,
        "S26": 1000,   # misma cadencia que S17: es la misma pantalla con otro panel
        "S23": 1000,   # diálogo modal breve; el latch del destino se captura al detectarlo
        "S29": 1000,   # gemelo de S23 para armas: mismo diálogo, misma cadencia
        "S30": 1500,   # inventario de amplificadores: misma cadencia que S9, es la misma grilla
        "S25": 1000,   # diálogo de confirmación del desmontaje: una sola lectura alcanza (no lee
                       #   nada de la pantalla, solo congela el conteo ya declarado)
        # S11: 5000 → 300. Antes solo hacía falta RECONOCERLA para no capturar; ahora se sigue
        # una selección que el usuario hace clickeando cada 1-2 s, y cada ciclo perdido es un
        # disco sin datos. El censo de tildes (lo que corre siempre) es < 3 ms sin OCR; el OCR
        # del contador está gateado por firma y el del panel solo corre cuando hay apareo.
        "S11": 300,
        "S24": 500,    # modal de commit: vive hasta que el usuario aprieta Confirmar
        # Gacha. S27 es la antesala del evento y hay que estar despierto cuando arranca: es
        # quien arma el volcado de frames. S28 es estática y espera input (botón "Confirmar" +
        # "Pulsa un espacio en blanco para cerrar"), así que no hace falta apurarla.
        "S27": 400,
        "S28": 1000,
    }
    return cadence.get(state.code, 2000)
