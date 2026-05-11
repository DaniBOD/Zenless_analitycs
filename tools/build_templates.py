"""
Genera los templates PNG para el ScreenDetector (detector.py) recortando
regiones características de los screenshots de referencia en:
  Documentacion/Screenshots_Triggers/Discos_Triggers/

Salida: app/resources/templates/*.png

Ejecutar cada vez que cambien los screenshots de referencia o la UI del juego.
Las coordenadas son relativas a la resolución original del screenshot (normalizado 0-1).

Uso:
    python tools/build_templates.py [--show]   # --show abre cada crop con cv2.imshow
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
OUT  = ROOT / "app" / "resources" / "templates"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Definición de cada template:
#   name        → nombre del archivo de salida (debe coincidir con detector.py)
#   source      → imagen de referencia (relativa a REFS)
#   roi         → [x, y, w, h] normalizados (0-1) — zona característica del estado
#   description → para logs
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "name": "s2_resultado_desafio.png",
        "source": "01_Pantalla_Resultado_Desafio/Ejemplo_1.png",
        # Encabezado "RESULTADOS DEL DESAFÍO" — franja superior central
        "roi": [0.25, 0.04, 0.50, 0.07],
        "description": "S2 — encabezado resultado desafio",
    },
    {
        "name": "s3_modal_detalle_drop.png",
        "source": "02_Detalle_Disco_Desde_Resultado/Ejemplo_1.png",
        # ROI previa [0.50, 0.08, 0.45, 0.08] era una franja de fondo negro
        # texturado genérica → matcheaba cualquier panel oscuro (S16 set
        # detail, perfil de PJ, etc) con conf 0.85+.
        # Nueva ROI: footer "R Descartar / T Bloquear" del modal — texto
        # estático que aparece ÚNICAMENTE en este modal post-farmeo (los
        # otros modales similares como S16 'Información de conjunto' o el
        # perfil del PJ no tienen ese footer).
        "roi": [0.42, 0.870, 0.20, 0.030],
        "description": "S3 — footer 'R Descartar / T Bloquear' (modal post-farmeo)",
    },
    {
        "name": "s8_agente_driver.png",
        "source": "03_Pantalla_Agente_Discos_Equipados/Ejemplo_1.png",
        # Hexágono central con "DRIVER" visible
        "roi": [0.38, 0.22, 0.24, 0.20],
        "description": "S8 — hexagono DRIVER vista agente",
    },
    {
        "name": "s9_inventario_general.png",
        "source": "09_Inventario_discos_general/Ejemplo_1.png",
        # ROI previa solo cubría "Pistas de disco [3" — texto repetido en S17
        # (botón "Personalización de pistas de disco") → causa FP.
        # Nueva ROI: bloque vertical superior izquierdo que incluye breadcrumb
        # 'Ciudad' (y≈0.039) + header 'Pistas de disco' (y≈0.122). Esa pareja
        # de elementos solo aparece en el inventario global.
        "roi": [0.025, 0.025, 0.150, 0.130],
        "description": "S9 — header 'Pistas de disco' (inventario general)",
    },
    {
        "name": "s6_tienda_detalle_panel.png",
        "source": "04_Inventario_Disco_Vista_Individual/Ejemplo_6(vista_detallada_tienda_musica).png",
        # Panel lateral derecho con stats (vista tienda)
        "roi": [0.50, 0.08, 0.45, 0.08],
        "description": "S6 — panel detalle tienda musica",
    },
    {
        "name": "s5_resultado_afinacion.png",
        "source": "11_Tienda_Musica_Afinacion/Tienda_musica_afinacion.png",
        # Header "Resultado de afinación:"
        "roi": [0.02, 0.04, 0.45, 0.07],
        "description": "S5 — header resultado afinacion",
    },
    {
        "name": "s10_modal_upgrade.png",
        "source": "05_Upgrade_PRE_nivel0/Ejemplo_1.png",
        # Barra EXP verde + zona del nivel (parte inferior del modal)
        "roi": [0.30, 0.38, 0.40, 0.08],
        "description": "S10 — barra EXP modal upgrade",
    },
    {
        "name": "s11_desmontaje.png",
        "source": "12_Desmontaje/Ejemplo_1.png",
        # Header con título "Desmontaje" o botón principal — franja superior
        "roi": [0.02, 0.04, 0.35, 0.06],
        "description": "S11 — header desmontaje",
    },
    {
        "name": "s7_tienda_detalle_full.png",
        "source": "07_Upgrade_POST_animacion_confirmacion/Ejemplo_3(tienda_musica).png",
        # IMPORTANTE: usar un crop más distintivo que solo "Ciudad" arriba, porque
        # ese texto aparece también en otras pantallas (S13/S14). Usamos el panel
        # de stats derecho del modal que es exclusivo de S7.
        "roi": [0.50, 0.20, 0.40, 0.30],
        "description": "S7 — panel stats derecho (tienda musica fullscreen)",
    },
    {
        "name": "s13_seleccion_set_farmeo.png",
        "source": "13_Seleccion_set_farmeo/Ejemplo_1.png",
        # Header "Nivel de desafío Nivel 60" arriba-derecha
        "roi": [0.55, 0.015, 0.30, 0.05],
        "description": "S13 — header 'Nivel de desafío' (seleccion set farmeo)",
    },
    # ---- Triggers generales (no específicos de captura de discos) ----
    # Path relativo es desde la raíz de Screenshots_Triggers (no Discos_Triggers/).
    # build_templates resuelve esto via la flag source_relative_to_root.
    {
        "name": "s14_seleccion_equipo_combate.png",
        "source": "../Triggers_Generales/Seleecion_Equipo_Combate/Ejemplo_1.png",
        # Contador "3/3" + emoji amarillo en esquina superior derecha
        "roi": [0.85, 0.005, 0.13, 0.06],
        "description": "S14 — contador '3/3' (seleccion equipo pre-combate)",
    },
    {
        "name": "s15_menu_personajes.png",
        "source": "../Triggers_Generales/Menu_Personajes/Ejemplo_1.png",
        # Header "Plan de entrenamiento" arriba-izquierda
        "roi": [0.05, 0.015, 0.22, 0.05],
        "description": "S15 — header 'Plan de entrenamiento' (menu personajes)",
    },
    {
        "name": "s16_detalle_set_disco.png",
        "source": "../Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_1.png",
        # Texto "Información de conjunto" del modal de detalle de set.
        # Es ESTÁTICO entre todos los sets (a diferencia del nombre del set
        # arriba) y aparece SOLO en este modal. Anti-FP crítico vs S3.
        "roi": [0.325, 0.420, 0.180, 0.025],
        "description": "S16 — 'Información de conjunto' (modal detalle set)",
    },
    {
        "name": "s17_personalizacion_pistas.png",
        "source": "04_Inventario_Disco_Vista_Individual/Ejemplo_1.png",
        # Pantalla "Personalización de pistas de disco" cuando el usuario
        # clickea un disco equipado en el PJ y se abre el panel lateral.
        # Distintiva por el footer "Comparar / Recomendado" abajo-izquierda
        # (combo de botones único de esta pantalla — no aparece en S8 ni en
        # los modales S3/S6/S7).
        "roi": [0.050, 0.935, 0.220, 0.040],
        "description": "S17 — footer 'Comparar / Recomendado' (vista detalle disco PJ)",
    },
]


def crop_roi(img: np.ndarray, roi: list[float]) -> np.ndarray:
    h, w = img.shape[:2]
    x = int(roi[0] * w)
    y = int(roi[1] * h)
    rw = int(roi[2] * w)
    rh = int(roi[3] * h)
    return img[y:y + rh, x:x + rw]


def _resolve_source(source_rel: str) -> Path:
    """
    Resuelve rutas relativas a REFS. Soporta '..' para escapar a otras
    subcarpetas dentro de Screenshots_Triggers/ (ej. Triggers_Generales/).
    """
    return (REFS / source_rel).resolve()


def build(show: bool = False) -> int:
    ok = 0
    for t in TEMPLATES:
        src_path = _resolve_source(t["source"])
        out_path = OUT / t["name"]

        if not src_path.exists():
            if t.get("optional"):
                print(f"  [SKIP] {t['name']} — source no encontrado (opcional): {src_path.name}")
                continue
            print(f"  [FAIL] {t['name']} — source no encontrado: {src_path}")
            continue

        img = cv2.imread(str(src_path))
        if img is None:
            print(f"  [FAIL] {t['name']} — no se pudo leer: {src_path}")
            continue

        crop = crop_roi(img, t["roi"])
        if crop.size == 0:
            print(f"  [FAIL] {t['name']} — crop vacío con roi={t['roi']}")
            continue

        cv2.imwrite(str(out_path), crop)
        print(f"  [OK]   {t['name']} ({crop.shape[1]}x{crop.shape[0]}) — {t['description']}")
        ok += 1

        if show:
            cv2.imshow(t["name"], crop)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="Mostrar cada crop con cv2.imshow")
    args = parser.parse_args()

    print(f"Generando templates en {OUT}...")
    n = build(show=args.show)
    print(f"\n[{n}/{len(TEMPLATES)}] templates generados.")
    if n < len([t for t in TEMPLATES if not t.get("optional")]):
        sys.exit(1)


if __name__ == "__main__":
    main()
