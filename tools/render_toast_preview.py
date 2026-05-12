"""
Renderiza los 4 variants del toast (equipar / mejorar / reserva / descartar)
a PNG para auto-validar la UI sin abrir el juego.

Output: Documentacion/QA/calibracion_visual/toast_previews/<variant>.png
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)

    from app.ui.toast import DiscToast, ToastData
    from app.core.asset_resolver import set_logo_path, agent_avatar_path

    out_dir = REPO / "Documentacion" / "QA" / "calibracion_visual" / "toast_previews"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _logo(en: str) -> str | None:
        p = set_logo_path(en)
        return str(p) if p else None

    def _avatar(name_es: str, variant: str = "extend") -> str | None:
        p = agent_avatar_path(name_es, variant=variant)
        return str(p) if p else None

    samples = {
        "equipar": ToastData(
            variant="equipar",
            disc_id=482,
            set_name="Tecno Pícido",
            slot=4,
            rarity="S",
            main_stat="ATK %",
            main_value="30 %",
            subs_summary="CR · CD · ATK% · ATK",
            target_agent="Yanagi",
            target_mind=2,
            score=87.3,
            urgency=0.85,
            threshold=0.75,
            set_logo=_logo("Woodpecker Electro"),
            target_avatar=_avatar("Yanagi"),
        ),
        "mejorar": ToastData(
            variant="mejorar",
            disc_id=312,
            set_name="Floración del alba",
            slot=6,
            rarity="S",
            main_stat="DMG Eléctrico",
            main_value="30 %",
            subs_summary="CR · CD · ATK · PEN",
            target_agent="Cissia",
            target_mind=0,
            score=72.1,
            urgency=0.65,
            threshold=0.50,
            set_logo=_logo("Dawn's Bloom"),
            target_avatar=_avatar("Cissia"),
        ),
        "reserva": ToastData(
            variant="reserva",
            disc_id=193,
            set_name="Nana a la luz cenicienta",
            slot=2,
            rarity="S",
            main_stat="ATK",
            main_value="316",
            subs_summary="CR · CD · ER · HP%",
            target_agent="—",
            target_mind=0,
            score=58.4,
            urgency=0.45,
            threshold=0.50,
            set_logo=_logo("Moonlight Lullaby"),
        ),
        "descartar": ToastData(
            variant="descartar",
            disc_id=78,
            set_name="Polar Metal",
            slot=3,
            rarity="A",
            main_stat="DEF %",
            main_value="24 %",
            subs_summary="DEF · HP · HP% · PB",
            target_agent="—",
            target_mind=0,
            score=22.8,
            urgency=0.20,
            threshold=0.50,
            set_logo=_logo("Polar Metal"),
        ),
    }

    rendered = []

    def render_next():
        if not samples:
            print("\nResultado:")
            for name, path in rendered:
                print(f"  {name:10s} -> {path}")
            app.quit()
            return
        name, data = samples.popitem()
        toast = DiscToast()
        toast.show_recommendation(data)
        # Esperar a que termine el fade-in (220ms) y al primer tick (100ms)
        QTimer.singleShot(500, lambda t=toast, n=name: capture_and_next(t, n))

    def capture_and_next(toast, name):
        # Grab del widget completo (incluye glow padding)
        pixmap = toast.grab()
        out_path = out_dir / f"toast_{name}.png"
        pixmap.save(str(out_path), "PNG")
        rendered.append((name, out_path.relative_to(REPO)))
        toast.hide()
        toast.deleteLater()
        QTimer.singleShot(50, render_next)

    QTimer.singleShot(300, render_next)
    app.exec()


if __name__ == "__main__":
    main()
