"""Structural tests for the local open-source runtime shape."""

from __future__ import annotations

import tomllib
import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestLocalModeStructure(unittest.TestCase):
    def test_pyproject_does_not_reference_deleted_readme(self) -> None:
        """Packaging metadata should not require a README that is intentionally absent."""
        pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

        self.assertNotIn("readme", pyproject["project"])

    def test_productized_runtime_surfaces_are_removed(self) -> None:
        """Local mode should not carry Docker, Redis worker, auth, billing, or ops routes."""
        removed_paths = [
            PROJECT_ROOT / "docker",
            PROJECT_ROOT / "apps" / "worker.py",
            PROJECT_ROOT / "server" / "routers" / "auth.py",
            PROJECT_ROOT / "server" / "routers" / "billing.py",
            PROJECT_ROOT / "server" / "routers" / "billing_old.py",
            PROJECT_ROOT / "server" / "routers" / "ops.py",
            PROJECT_ROOT / "server" / "routers" / "user.py",
            PROJECT_ROOT / "server" / "services" / "queue_service.py",
            PROJECT_ROOT / "server" / "services" / "redis_client.py",
            PROJECT_ROOT / "server" / "services" / "workflow_runner_service.py",
        ]

        for path in removed_paths:
            with self.subTest(path=path):
                self.assertFalse(path.exists())

    def test_runtime_dependencies_exclude_removed_services(self) -> None:
        """Runtime dependency list should match the local single-process app."""
        pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
        deps = {dep.split("[", 1)[0].split(">=", 1)[0].lower() for dep in pyproject["project"]["dependencies"]}

        for removed_dependency in {"stripe", "redis", "bcrypt", "flask", "pyjwt"}:
            with self.subTest(dependency=removed_dependency):
                self.assertNotIn(removed_dependency, deps)

    def test_static_local_ui_exists(self) -> None:
        """FastAPI should serve the built React workspace UI from the project itself."""
        index_html = PROJECT_ROOT / "server" / "static" / "index.html"
        html = index_html.read_text()

        self.assertTrue(index_html.exists())
        self.assertIn('id="root"', html)
        self.assertIn("/static/assets/", html)

    def test_react_tldraw_frontend_source_exists(self) -> None:
        """The local browser UI should use React and tldraw for draggable canvas objects."""
        package_json = json.loads((PROJECT_ROOT / "web" / "package.json").read_text())
        dependencies = package_json["dependencies"]
        media_canvas_source = (PROJECT_ROOT / "web" / "src" / "components" / "MediaCanvas.tsx").read_text()
        app_source = (PROJECT_ROOT / "web" / "src" / "App.tsx").read_text()

        self.assertIn("react", dependencies)
        self.assertIn("tldraw", dependencies)
        self.assertIn("<Tldraw", media_canvas_source)
        self.assertIn("editor.createAssets", media_canvas_source)
        self.assertIn("editor.createShape", media_canvas_source)
        self.assertIn('fetch("/chat"', (PROJECT_ROOT / "web" / "src" / "api.ts").read_text())
        self.assertIn("Thinking process", (PROJECT_ROOT / "web" / "src" / "components" / "ChatPanel.tsx").read_text())
        self.assertIn("MediaCanvas", app_source)
        self.assertIn('content: payload.text || payload.final_output_text || "Task completed."', app_source)
        self.assertNotIn('content: payload.final_output_text || payload.text || "Task completed."', app_source)

    def test_static_local_ui_uses_english_copy(self) -> None:
        """The open-source local UI source should be English-only for public release."""
        ui_files = [
            PROJECT_ROOT / "server" / "static" / "index.html",
            *sorted((PROJECT_ROOT / "web" / "src").rglob("*.ts")),
            *sorted((PROJECT_ROOT / "web" / "src").rglob("*.tsx")),
            *sorted((PROJECT_ROOT / "web" / "src").rglob("*.css")),
        ]

        for path in ui_files:
            with self.subTest(path=path):
                self.assertIsNone(re.search(r"[\u4e00-\u9fff]", path.read_text()))

    def test_local_auth_uses_configured_default_user(self) -> None:
        """Local mode should resolve a user without requiring a login token."""
        auth_source = (PROJECT_ROOT / "server" / "utils" / "session_auth.py").read_text()

        self.assertIn("SYS_CONFIG.user_id_default", auth_source)
        self.assertNotIn("jwt.decode", auth_source)

    def test_default_local_port_is_not_occupied_development_port(self) -> None:
        """Default local startup files should use the current non-conflicting port."""
        system_config = json.loads((PROJECT_ROOT / "conf" / "jsons" / "system.json").read_text())

        self.assertEqual(system_config["api_port"], 9502)
        for path in [
            PROJECT_ROOT / ".env.template",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "scripts" / "start_local.sh",
            PROJECT_ROOT / "server" / "main.py",
        ]:
            with self.subTest(path=path):
                self.assertIn("9502", path.read_text())
                self.assertNotIn("9501", path.read_text())


if __name__ == "__main__":
    unittest.main()
