import os
import subprocess
from pathlib import Path

from .constants import ERROR_SYMBOL, GOOD_SYMBOL, INFO_SYMBOL, SUCCESS_SYMBOL, WARNING_SYMBOL, console
from .settings import get_settings


def snake_to_pascal(snake_str: str) -> str:
    components = snake_str.split('_')
    return ''.join(x.capitalize() for x in components)


def run_command(command: list[str], cwd: Path | None = None, verbose: bool = False) -> tuple[bool, str, str]:
    """Wrapper to Run a system command and handle errors."""

    env = os.environ.copy()

    settings = get_settings()

    # Prepend new path to existing PATH
    current_path = env.get('PATH', '')
    env['PATH'] = f'{settings.install_dir / "bin"}:{current_path}'

    if cwd is None:
        cwd = Path.cwd()

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, cwd=cwd, env=env)  # noqa: S603
    except subprocess.CalledProcessError as e:
        if verbose:
            console.print(f'{e.stdout}')
            console.print(f'{e.stderr}')
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        return False, 'Executable not found', ''
    else:
        if verbose:
            console.print(f'{result.stdout}')
        return True, result.stdout, result.stderr


def _get_venv_path() -> Path:
    venv = os.environ.get('VIRTUAL_ENV')
    if not venv:
        raise RuntimeError('No virtual environment activated')
    return Path(venv)


def safe_relative_path(path: Path, base: Path) -> Path:
    try:
        return path.relative_to(base)
    except ValueError:
        return Path('..') / path.name  # or use os.path.relpath()
