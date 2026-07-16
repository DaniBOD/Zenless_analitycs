"""
tools/run_pipeline_on_screenshots.py — Test E2E del pipeline OCR sin abrir el juego.

Recorre todos los screenshots reales en
Documentacion/Screenshots_Triggers/Discos_Triggers/, los pasa por:

    capturer.crop_named_roi → ocr_tesseract → parser_disc.parse_modal_detalle
                                            → recommender.recomendar (si DB cargada)

y genera un reporte markdown con:
- por imagen: estado, título OCR, slot, mainstat, substats, confianza global
- por estado (S3, S6, S10): promedio confianza, % de slots detectados, % stats canónicos

Output:  audit/calibracion_<YYYYMMDD_HHMMSS>.md

Si Tesseract no está instalado, exit 2 con instrucciones de instalación.

Uso:
    python tools/run_pipeline_on_screenshots.py
    python tools/run_pipeline_on_screenshots.py --state S3
    python tools/run_pipeline_on_screenshots.py --tesseract-cmd "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SCREENSHOTS_ROOT = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
AUDIT_DIR = REPO / "audit"

# Carpeta → estado lógico para asignar al pipeline
FOLDER_TO_STATE: dict[str, str] = {
    "02_Detalle_Disco_Desde_Resultado":       "S3",
    "04_Inventario_Disco_Vista_Individual":   "S6",
    "05_Upgrade_PRE_nivel0":                  "S10",
    "06_Upgrade_PRE_nivel3_6_9_12":           "S10",
    "07_Upgrade_POST_animacion_confirmacion": "S10",
    "19_Upgrade_PRE_materiales_cargados":     "S10",
}

INSTALL_HINT = """
Tesseract OCR no esta disponible. Para instalarlo en Windows:

    winget install UB-Mannheim.TesseractOCR

Despues agregar al PATH (o pasar --tesseract-cmd con la ruta absoluta):

    "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

Verificar instalacion:

    tesseract --version

Y descargar pack de idioma espanol (spa) si no viene incluido:
https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata
-> copiar a  C:\\Program Files\\Tesseract-OCR\\tessdata\\
"""


def find_tesseract_executable() -> str | None:
    """Busca el binario de Tesseract en ubicaciones comunes de Windows."""
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def load_image(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", help="Filtrar por estado (S3, S6, S10)")
    parser.add_argument("--tesseract-cmd", help="Ruta al ejecutable tesseract.exe")
    args = parser.parse_args()

    # --- Detección de Tesseract ---
    try:
        import pytesseract
    except ImportError:
        print("ERROR: pytesseract no instalado.")
        print("  pip install pytesseract")
        sys.exit(2)

    tess_cmd = args.tesseract_cmd or find_tesseract_executable()
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        print(f"ERROR: tesseract.exe no disponible ({e}).")
        print(INSTALL_HINT)
        sys.exit(2)

    # --- Importar componentes ---
    from app.core.ocr_tesseract import TesseractBackend
    from app.core.parser_disc import parse_modal_detalle

    ocr = TesseractBackend(tesseract_cmd=tess_cmd)

    # --- Set repo opcional (si la DB está disponible) ---
    set_repo = None
    try:
        from app.db.connection import get_connection
        from app.db.repositories import DiscSetRepo
        con = get_connection()
        set_repo = DiscSetRepo(con)
    except Exception as exc:
        print(f"[warn] DB no disponible para set lookup: {exc}")

    # --- Recolectar screenshots ---
    by_state: dict[str, list[tuple[str, Path]]] = {}
    for folder_name, state in FOLDER_TO_STATE.items():
        if args.state and state != args.state:
            continue
        folder = SCREENSHOTS_ROOT / folder_name
        if not folder.exists():
            continue
        for img_path in sorted(folder.glob("*.png")):
            by_state.setdefault(state, []).append((folder_name, img_path))

    if not by_state:
        print("No se encontraron screenshots para procesar.")
        sys.exit(0)

    # --- Procesar ---
    results: list[dict] = []
    for state, items in by_state.items():
        print(f"\n=== {state} ({len(items)} imágenes) ===")
        for folder_name, img_path in items:
            img = load_image(img_path)
            if img is None:
                print(f"  [skip] {img_path.name} — no se pudo cargar")
                continue
            try:
                disc = parse_modal_detalle(img, ocr, set_repo, state_code=state)
            except Exception as exc:
                print(f"  [error] {img_path.name}: {exc}")
                results.append({
                    "state": state, "folder": folder_name, "file": img_path.name,
                    "error": str(exc),
                })
                continue

            n_subs_canon = sum(1 for s in disc.subs if s.nombre_canon)
            print(
                f"  {img_path.name[:40]:<40}  "
                f"slot={disc.slot}  "
                f"main={(disc.main_stat_canon or '?')[:18]:<18}  "
                f"subs={len(disc.subs)} ({n_subs_canon} canon)  "
                f"conf={disc.confianza_global:.2f}"
            )
            results.append({
                "state": state,
                "folder": folder_name,
                "file": img_path.name,
                "titulo_raw": disc.set_name_raw,
                "set_canon": disc.set_name_canon,
                "slot": disc.slot,
                "nivel": disc.nivel,
                "rareza": disc.rareza,
                "main_raw": disc.main_stat_raw,
                "main_canon": disc.main_stat_canon,
                "main_valor": disc.main_valor,
                "subs": [
                    {
                        "nombre_raw": s.nombre_raw,
                        "nombre_canon": s.nombre_canon,
                        "valor": s.valor,
                        "rolls": s.rolls,
                    }
                    for s in disc.subs
                ],
                "confianza_global": disc.confianza_global,
                "notas": disc.notas,
            })

    # --- Generar reporte markdown ---
    AUDIT_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = AUDIT_DIR / f"calibracion_{ts}.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Reporte de calibración OCR — {ts}\n\n")
        f.write(f"Pipeline: capturer → ocr_tesseract → parser_disc\n\n")
        f.write(f"Tesseract: `{tess_cmd or 'PATH'}`  ·  ")
        f.write(f"Total imágenes procesadas: **{len([r for r in results if 'error' not in r])}**\n\n")

        # Resumen por estado
        f.write("## Resumen por estado\n\n")
        f.write("| Estado | Imgs | Slot detectado | Main canon | Subs canon avg | Confianza avg |\n")
        f.write("|--------|------|----------------|------------|----------------|---------------|\n")
        for state in sorted(by_state.keys()):
            state_results = [r for r in results if r.get("state") == state and "error" not in r]
            if not state_results:
                continue
            n = len(state_results)
            slot_ok = sum(1 for r in state_results if r["slot"] >= 1)
            main_ok = sum(1 for r in state_results if r["main_canon"])
            sub_canon_avg = sum(
                sum(1 for s in r["subs"] if s["nombre_canon"]) / max(1, len(r["subs"]))
                for r in state_results
            ) / n
            conf_avg = sum(r["confianza_global"] for r in state_results) / n
            f.write(
                f"| {state} | {n} | {slot_ok}/{n} | {main_ok}/{n} | "
                f"{sub_canon_avg:.0%} | {conf_avg:.2f} |\n"
            )

        # Detalle imagen por imagen
        for state in sorted(by_state.keys()):
            f.write(f"\n## {state} — detalle\n\n")
            state_results = [r for r in results if r.get("state") == state]
            for r in state_results:
                f.write(f"### `{r['file']}`\n\n")
                if "error" in r:
                    f.write(f"⚠️ Error: {r['error']}\n\n")
                    continue
                f.write(f"- Título raw: `{r['titulo_raw']}`  → set canon: `{r['set_canon']}`  · slot: `{r['slot']}`\n")
                f.write(f"- Nivel: `{r['nivel']}`  ·  Rareza: `{r['rareza']}`\n")
                f.write(f"- Main: `{r['main_raw']}` → `{r['main_canon']}` valor=`{r['main_valor']}`\n")
                if r["subs"]:
                    f.write(f"- Substats:\n")
                    for s in r["subs"]:
                        f.write(
                            f"  - raw=`{s['nombre_raw']}` canon=`{s['nombre_canon']}` "
                            f"valor=`{s['valor']}` rolls=`{s['rolls']}`\n"
                        )
                f.write(f"- Confianza global: **{r['confianza_global']:.2f}**\n")
                if r["notas"]:
                    f.write(f"- Notas: {', '.join(r['notas'])}\n")
                f.write("\n")

    print(f"\nReporte: {report_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
