"""
Debug: corre todos los templates contra los 4 screenshots de falso positivo
de set detail (modal 'Información de conjunto') y reporta la confianza
de cada template. Si S3 saca > S16, ese es el bug.
"""
from __future__ import annotations
import sys
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.detector import ScreenDetector, _STATE_TEMPLATES, TEMPLATES_DIR

FPS = ROOT / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos"
PROFILES = ROOT / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente"


def test_image(img_path: Path):
    print(f"\n=== {img_path.name} ===")
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"  FAIL: no se pudo leer")
        return
    print(f"  shape: {img.shape}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    results = []
    for entry in _STATE_TEMPLATES:
        tmpl_path = TEMPLATES_DIR / entry["template"]
        if not tmpl_path.exists():
            continue
        tmpl = cv2.imread(str(tmpl_path))
        if tmpl is None:
            continue
        gtmpl = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if tmpl.ndim == 3 else tmpl
        if gtmpl.shape[0] > gray.shape[0] or gtmpl.shape[1] > gray.shape[1]:
            continue
        m = cv2.matchTemplate(gray, gtmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(m)
        results.append((entry["code"], entry["template"], max_val, max_loc, gtmpl.shape))

    results.sort(key=lambda r: -r[2])
    for code, name, conf, loc, shape in results[:8]:
        marker = " <-- GANARIA" if conf >= 0.85 else ""
        print(f"  {code:4s} conf={conf:.3f}  tmpl={shape[1]}x{shape[0]}  pos={loc}  {name}{marker}")


if __name__ == "__main__":
    print("\n##### SET DETAIL MODALS (esperado: gana S16) #####")
    for i in range(1, 5):
        p = FPS / f"Detalle_set_disco_ejemplo_{i}.png"
        if p.exists():
            test_image(p)
    print("\n##### PERFIL AGENTE ATRIBUTOS BASE (esperado: gana S18) #####")
    for i in range(1, 7):
        p = PROFILES / f"atributos_base_ejemplo_{i}.png"
        if p.exists():
            test_image(p)
