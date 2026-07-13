#!/usr/bin/env python3
"""Interactive OAuth login helper for OpenAI Codex models."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from pathlib import Path


def _reexec_with_project_venv() -> None:
    """Use the project virtual environment when the script is run directly."""
    script_path = Path(__file__).resolve()
    venv_python = script_path.parents[1] / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return
    current = Path(sys.executable).resolve()
    if current == venv_python.resolve():
        return
    os.execv(str(venv_python), [str(venv_python), str(script_path), *sys.argv[1:]])


def main() -> int:
    """Run an interactive OpenAI Codex OAuth login."""
    try:
        from oauth_cli_kit import get_token
        from oauth_cli_kit import login_oauth_interactive
    except ImportError:
        print("oauth-cli-kit is not installed. Run scripts/start_local.sh first.")
        return 1

    token = None
    with suppress(Exception):
        token = get_token()

    if not (token and getattr(token, "access", None)):
        print("Starting interactive OpenAI Codex OAuth login.")
        token = login_oauth_interactive(print_fn=print, prompt_fn=input)

    if not (token and getattr(token, "access", None)):
        print("OpenAI Codex authentication failed.")
        return 1

    print(f"Authenticated with OpenAI Codex account: {token.account_id}")
    return 0


if __name__ == "__main__":
    _reexec_with_project_venv()
    raise SystemExit(main())
