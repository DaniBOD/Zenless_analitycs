"""
tools/annotate_rois.py — Validación visual de ROIs.

Toma cada screenshot real en Documentacion/Screenshots_Triggers/Discos_Triggers/,
le pinta encima los rectángulos definidos en app/config/rois.toml para el estado
correspondiente, y exporta las imágenes anotadas a:

    Documentacion/QA/calibracion_visual/<estado>/<nombre>_anotado.png

Uso:
    python tools/annotate_rois.py            # procesa todos
    python tools/annotate_rois.py --state S3 # filtra por estado
    python tools/annotate_rois.py --check    # exit-code != 0 si encuentra ROIs fuera del frame

Cada ROI se pinta con un color único + label + coords absolutas en píxeles.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
SCREENSHOTS_ROOT = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
ROIS_TOML = REPO / "app" / "config" / "rois.toml"
OUTPUT_ROOT = REPO / "Documentacion" / "QA" / "calibracion_visual"

# Mapping carpeta → (estado, sección_rois en toml)
# Nota: 04/Ejemplo_6 y 04/Ejemplo_7 son S6 (vista detallada tienda música).
#       El resto de 04/* es S9 (inventario individual fullscreen) — usa S6 como aprox.
FOLDER_TO_STATE: dict[str, tuple[str, str]] = {
    "01_Pantalla_Resultado_Desafio":          ("S2", None),                  # detección, no ROI
    "02_Detalle_Disco_Desde_Resultado":       ("S3", "modal_detalle_s3"),
    "03_Pantalla_Agente_Discos_Equipados":    ("S8", "agente_equipados"),
    "04_Inventario_Disco_Vista_Individual":   ("S6", "modal_detalle_s6"),
    "05_Upgrade_PRE_nivel0":                  ("S10", "modal_upgrade_s10"),
    "06_Upgrade_PRE_nivel3_6_9_12":           ("S10", "modal_upgrade_s10"),
    "07_Upgrade_POST_animacion_confirmacion": ("S10", "modal_upgrade_s10"),
    "08_Pantallas_Menu_Transicion":           ("S1", None),
    "11_Tienda_Musica_Afinacion":             ("S5", None),
    "12_Desmontaje":                          ("S11", None),
}

# Override por nombre de archivo: cuando el detector y el parser deben tratar
# una imagen dentro de una carpeta como un estado distinto al default de la carpeta.
# Ej: Ejemplo_3(tienda_musica) está físicamente en la carpeta 07 (POST upgrade) pero
# es visualmente S7 (tienda música fullscreen).
FILENAME_OVERRIDES: dict[str, tuple[str, str]] = {
    "Ejemplo_3(tienda_musica).png":       ("S7", "modal_detalle_s7"),
    "Ejemplo_1(tienda_musica).png":       ("S7", "modal_detalle_s7"),
    "Ejemplo_2(tienda_musica).png":       ("S7", "modal_detalle_s7"),
}

# Paleta de colores BGR para diferenciar ROIs (cv2 usa BGR)
COLORS = [
    (0, 255, 255),    # amarillo
    (0, 255, 0),      # verde
    (255, 0, 255),    # magenta
    (255, 128, 0),    # azul claro
    (0, 128, 255),    # naranja
    (255, 255, 0),    # cyan
    (0, 0, 255),      # rojo
    (180, 105, 255),  # rosa
    (50, 200, 50),    # verde oscuro
    (200, 200, 0),    # cyan oscuro
    (128, 0, 255),    # violeta
    (50, 150, 255),   # naranja medio
]


def load_rois() -> dict:
    with open(ROIS_TOML, "rb") as f:
        return tomllib.load(f)


def get_section_keys(rois: dict, section: str) -> list[tuple[str, list[float]]]:
    """Devuelve solo las entradas que son ROIs (lista de 4 floats)."""
    out = []
    for k, v in rois.get(section, {}).items():
        if isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
            out.append((k, v))
    return out


def annotate(img: np.ndarray, rois_section: list[tuple[str, list[float]]]) -> tuple[np.ndarray, list[str]]:
    """
    Pinta ROIs sobre img. Devuelve la imagen anotada y una lista de issues
    detectados (ej: ROI fuera del frame).
    """
    out = img.copy()
    h, w = img.shape[:2]
    issues: list[str] = []

    for idx, (name, roi) in enumerate(rois_section):
        x = int(roi[0] * w)
        y = int(roi[1] * h)
        rw = int(roi[2] * w)
        rh = int(roi[3] * h)
        color = COLORS[idx % len(COLORS)]

        # Detectar ROIs fuera del frame
        if x < 0 or y < 0 or x + rw > w or y + rh > h:
            issues.append(f"{name}: fuera del frame ({x},{y},{rw},{rh}) en {w}x{h}")

        # Rectángulo
        cv2.rectangle(out, (x, y), (x + rw, y + rh), color, 2)

        # Label con fondo opaco
        label = f"{name}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)

        # Posicionar label arriba del rectángulo si hay espacio, sino abajo
        label_y = y - 6 if y - 6 - th >= 0 else y + rh + th + 6
        label_x = x

        # Fondo del label
        cv2.rectangle(
            out,
            (label_x, label_y - th - 4),
            (label_x + tw + 4, label_y + 2),
            (0, 0, 0),
            cv2.FILLED,
        )
        cv2.putText(out, label, (label_x + 2, label_y - 2), font, scale, color, thickness, cv2.LINE_AA)

    # Watermark con resolución y nombre de la sección
    info = f"{w}x{h}  ROIs: {len(rois_section)}"
    cv2.rectangle(out, (10, 10), (10 + 8 + 7 * len(info), 36), (0, 0, 0), cv2.FILLED)
    cv2.putText(out, info, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    return out, issues


def process_folder(folder: Path, state: str, section: str | None, rois: dict, out_root: Path) -> dict:
    """Procesa todas las imágenes de una carpeta."""
    stats = {"folder": folder.name, "state": state, "processed": 0, "issues": [], "skipped": 0}

    if section is None:
        stats["skipped"] = sum(1 for _ in folder.glob("*.png"))
        return stats

    rois_section = get_section_keys(rois, section)
    if not rois_section:
        stats["issues"].append(f"sección '{section}' no encontrada o vacía en rois.toml")
        return stats

    for img_path in sorted(folder.glob("*.png")):
        # Override por nombre si aplica (ej. Ejemplo_3(tienda_musica) -> S7)
        override = FILENAME_OVERRIDES.get(img_path.name)
        if override:
            this_state, this_section_name = override
            this_section = get_section_keys(rois, this_section_name)
            if not this_section:
                stats["issues"].append(f"{img_path.name}: override apunta a sección inexistente {this_section_name}")
                continue
        else:
            this_state = state
            this_section = rois_section

        out_dir = out_root / this_state / folder.name
        out_dir.mkdir(parents=True, exist_ok=True)

        # OpenCV no abre rutas con caracteres unicode en Windows; usar np.fromfile
        data = np.fromfile(str(img_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            stats["issues"].append(f"no se pudo cargar: {img_path.name}")
            continue

        annotated, issues = annotate(img, this_section)
        stats["processed"] += 1
        for iss in issues:
            stats["issues"].append(f"{img_path.name}: {iss}")

        out_path = out_dir / f"{img_path.stem}_anotado.png"
        ok, buf = cv2.imencode(".png", annotated)
        if ok:
            buf.tofile(str(out_path))

    return stats


def main():
    parser = argparse.ArgumentParser(description="Anota ROIs sobre screenshots reales para validación visual")
    parser.add_argument("--state", help="Filtrar por estado (S2, S3, S6, S8, S10)")
    parser.add_argument("--check", action="store_true", help="Exit code != 0 si hay ROIs fuera del frame")
    args = parser.parse_args()

    if not SCREENSHOTS_ROOT.exists():
        print(f"ERROR: no existe {SCREENSHOTS_ROOT}", file=sys.stderr)
        sys.exit(1)
    if not ROIS_TOML.exists():
        print(f"ERROR: no existe {ROIS_TOML}", file=sys.stderr)
        sys.exit(1)

    rois = load_rois()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"[in]  Screenshots: {SCREENSHOTS_ROOT}")
    print(f"[in]  ROIs:        {ROIS_TOML}")
    print(f"[out] Output:      {OUTPUT_ROOT}")
    print()

    total_processed = 0
    total_issues = 0

    for folder_name, (state, section) in FOLDER_TO_STATE.items():
        folder = SCREENSHOTS_ROOT / folder_name
        if not folder.exists():
            continue
        if args.state and state != args.state:
            continue

        stats = process_folder(folder, state, section, rois, OUTPUT_ROOT)
        total_processed += stats["processed"]
        total_issues += len(stats["issues"])

        marker = "[skip]" if section is None else "[ok]  "
        line = f"{marker} {state:>3}  {folder_name:<45} {stats['processed']:>2} imgs"
        if stats["skipped"]:
            line += f"  (skipped {stats['skipped']})"
        if stats["issues"]:
            line += f"  !! {len(stats['issues'])} issues"
        print(line)
        for iss in stats["issues"]:
            print(f"        !!  {iss}")

    print()
    print(f"Total procesadas: {total_processed}")
    print(f"Total issues:     {total_issues}")
    print()
    if total_processed:
        print(f"Revisar las imagenes anotadas en {OUTPUT_ROOT}")

    if args.check and total_issues > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
