"""Testes isolados da navegacao principal do Dealer Hub (sem banco)."""
from __future__ import annotations

import ast
import html
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FakeStreamlit:
    def __init__(self, clicked: str | None = None):
        self.clicked = clicked
        self.calls: list[tuple[str, dict]] = []
        self.session_state = {"dh_active_page": "dashboard"}
        self.sidebar = self
        self.reruns = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def container(self, **_):
        return self

    def popover(self, *_args, **_kwargs):
        return self

    def columns(self, *_args, **_kwargs):
        return self, self, self

    def caption(self, *_args, **_kwargs):
        pass

    def markdown(self, *_args, **_kwargs):
        pass

    def button(self, label, **kwargs):
        self.calls.append((label, kwargs))
        return kwargs.get("key") == self.clicked and not kwargs.get("disabled", False)

    def rerun(self):
        self.reruns += 1


def load_navigation(fake: FakeStreamlit):
    ui = (ROOT / "src/ui.py").read_text(encoding="utf-8")
    tree = ast.parse(ui)
    names = {"_nav_icon", "_nav_icon_svg", "sidebar_navigation", "render_main_navigation"}
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "st": fake,
        "html": html,
        "NAV_ICONS": {
            "dashboard": ":material/dashboard:",
            "import": ":material/upload_file:",
        },
        "NAV_SVG_PATHS": {
            "dashboard": '<circle cx="8" cy="8" r="2"/>',
            "import": '<path d="M1 1h3"/>',
        },
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "src/ui.py", "exec"), namespace)
    return namespace


class SidebarNavigationTests(unittest.TestCase):
    def setUp(self):
        self.allowed = [
            {"key": "dashboard", "label": "Visão Geral", "group": "Principal"},
            {"key": "import", "label": "Importações", "group": "Administração"},
        ]

    def test_sidebar_locked_and_current_selectors(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        ui = (ROOT / "src/ui.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn('initial_sidebar_state="locked"', app)
        self.assertIn('render_main_navigation(nav, selected)', app)
        self.assertIn('stSidebarCollapsedControl', ui)
        self.assertIn('stSidebarCollapseButton', ui)
        self.assertIn('streamlit>=1.59,<2', requirements)

    def test_import_shortcut_routes_user(self):
        fake = FakeStreamlit("dh_top_import_shortcut")
        load_navigation(fake)["render_main_navigation"](self.allowed, "dashboard")
        self.assertEqual(fake.session_state["dh_active_page"], "import")
        self.assertEqual(fake.reruns, 1)

    def test_restrict_import_shortcut_without_permission(self):
        fake = FakeStreamlit()
        load_navigation(fake)["render_main_navigation"](self.allowed[:1], "dashboard")
        self.assertFalse(any(x[1].get("key") == "dh_top_import_shortcut" for x in fake.calls))
        self.assertFalse(any(x[1].get("key") == "dh_top_nav_import" for x in fake.calls))

    def test_fallback_popover_routes_user(self):
        fake = FakeStreamlit("dh_top_nav_import")
        load_navigation(fake)["render_main_navigation"](self.allowed, "dashboard")
        self.assertEqual(fake.session_state["dh_active_page"], "import")
        self.assertEqual(fake.reruns, 1)

    def test_sidebar_routes_user(self):
        fake = FakeStreamlit("dh_nav_import")
        load_navigation(fake)["sidebar_navigation"](self.allowed)
        self.assertEqual(fake.session_state["dh_active_page"], "import")
        self.assertEqual(fake.reruns, 1)


if __name__ == "__main__":
    unittest.main()
