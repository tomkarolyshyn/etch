import datetime
import os
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

import typer
import typer.completion
from rich.console import Console

# Create a singleton console object and import it everywhere
console = Console()
app = typer.Typer(
    pretty_exceptions_show_locals=False,  # enable the showing of local variables in the exception
    pretty_exceptions_short=True,  # enable the short exception message
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
# app.add_typer(project.app, name='project', help='Manage the current project')
# app.add_typer(function.app, name='function', help='functions acceleration commands')
# app.add_typer(hw.app, name='hw', help='Hardware Kernel build commands')
# app.add_typer(setup.app, name='setup', help='System dependency installer for Etch')


__version__ = version('etch')


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f'etch {__version__}')
        raise typer.Exit()


# Add version callback with explicit option
@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, '--version', callback=version_callback, is_eager=True, help='Show version and exit'
    ),
) -> None:
    pass


@app.command(name='--install-completion', hidden=True)
def install_completion(shell: Annotated[str, typer.Option(help='Shell to install completion for')] = '') -> None:
    """Install tab completion for the bside command."""

    if not shell:
        # Auto-detect shell
        shell = os.environ.get('SHELL', '').split('/')[-1]

    try:
        console.print(f'Installing completion for {shell}...')
        # This will install completion for the current script
        completion_code = typer.completion.get_completion_script(
            shell=shell, prog_name='bside', complete_var='_BSIDE_COMPLETE'
        )

        # Installation depends on the shell
        if shell == 'bash':
            completion_file = Path.home() / '.bash_completion'
            completion_file.write_text(completion_code)
            console.print(f'[green]Completion installed to {completion_file}[/green]')
            console.print('Run: [bold]source ~/.bash_completion[/bold] or restart your shell')
        elif shell == 'zsh':
            completion_dir = Path.home() / '.zsh' / 'completions'
            completion_dir.mkdir(parents=True, exist_ok=True)
            completion_file = completion_dir / '_bside'
            completion_file.write_text(completion_code)
            console.print(f'[green]Completion installed to {completion_file}[/green]')
            console.print('Add to your ~/.zshrc: [bold]fpath=(~/.zsh/completions $fpath)[/bold]')
        elif shell == 'fish':
            completion_dir = Path.home() / '.config' / 'fish' / 'completions'
            completion_dir.mkdir(parents=True, exist_ok=True)
            completion_file = completion_dir / 'bside.fish'
            completion_file.write_text(completion_code)
            console.print(f'[green]Completion installed to {completion_file}[/green]')
        else:
            console.print(f'[yellow]Unsupported shell: {shell}[/yellow]')
            console.print('Supported shells: bash, zsh, fish')

    except Exception as e:
        console.print(f'[red]Error installing completion: {e}[/red]')


def main() -> None:
    app()


if __name__ == '__main__':
    main()
