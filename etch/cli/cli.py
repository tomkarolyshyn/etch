import datetime
import os
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

import typer
import typer.completion
from rich.table import Table

from ..util.settings import get_settings
from ..util.util import console

# Create a singleton console object and import it everywhere

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
        console.print(f'etch {__version__}')
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
    """Install tab completion for the etch command."""

    if not shell:
        # Auto-detect shell
        shell = os.environ.get('SHELL', '').split('/')[-1]

    try:
        console.print(f'Installing completion for {shell}...')
        # This will install completion for the current script
        completion_code = typer.completion.get_completion_script(
            shell=shell, prog_name='etch', complete_var='_ETCH_COMPLETE'
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
            completion_file = completion_dir / '_etch'
            completion_file.write_text(completion_code)
            console.print(f'[green]Completion installed to {completion_file}[/green]')
            console.print('Add to your ~/.zshrc: [bold]fpath=(~/.zsh/completions $fpath)[/bold]')
        elif shell == 'fish':
            completion_dir = Path.home() / '.config' / 'fish' / 'completions'
            completion_dir.mkdir(parents=True, exist_ok=True)
            completion_file = completion_dir / 'etch.fish'
            completion_file.write_text(completion_code)
            console.print(f'[green]Completion installed to {completion_file}[/green]')
        else:
            console.print(f'[yellow]Unsupported shell: {shell}[/yellow]')
            console.print('Supported shells: bash, zsh, fish')

    except Exception as e:
        console.print(f'[red]Error installing completion: {e}[/red]')


# create sub-apps
config_app = typer.Typer()
kernel_app = typer.Typer()
compile_app = typer.Typer()
prj_app = typer.Typer()

# add sub-apps to main app
app.add_typer(config_app, name='config', help='config commands')
app.add_typer(kernel_app, name='kernel', help='kernel commands')
app.add_typer(compile_app, name='compile', help='compile commands')
app.add_typer(prj_app, name='project', help='project commands')


############################################################
##  CONFIG COMMANDS
############################################################


@config_app.command('list')
def config_list(option: str = typer.Option('table', '--option', '-o', help='Output format: table, json, toml')) -> None:
    """Show current configuration settings."""
    table = Table(title='🔧 App Configuration Settings')
    table.add_column('Setting', style='cyan', no_wrap=True)
    table.add_column('Value', style='green')
    table.add_column('Type', style='yellow')

    settings = get_settings()

    config_dict = settings.model_dump(exclude_none=True)

    for key, value in config_dict.items():
        # Format the value for display
        if isinstance(value, Path):
            display_value = str(value)
        elif isinstance(value, bool):
            display_value = '✅ True' if value else '❌ False'
        elif value is None:
            display_value = '[dim]None[/dim]'
        else:
            display_value = str(value)

        table.add_row(key, display_value, type(value).__name__)

    console.print(table)


@config_app.command('init')
def config_init() -> None:
    """initiize the current directory for the etch"""
    # settings = get_settings()
    typer.Exit(0)


@config_app.command('install')
def config_install() -> None:
    """initiize the required tools for the etch"""
    # settings = get_settings()
    typer.Exit(0)


@config_app.command('check')
def config_check() -> None:
    """Check the current etch setup"""
    # settings = get_settings()
    typer.Exit(0)


############################################################
##  PROJECT COMMANDS
############################################################


@prj_app.command('create')
def prj_create(
    name: Annotated[str, typer.Argument(help='Name of the project')],
    # template: Annotated[ProjectTemplates, typer.Option(help='Name of the app template to use')],
    # board: Annotated[BoardTypes, typer.Option(help='Board to use')] = DEFAULT_BOARD,
    template: Annotated[str, typer.Option(help='Name of the app template to use')],
    board: Annotated[str, typer.Option(help='Board to use')],
    force: Annotated[bool, typer.Option(help='Force overwrite existing project')] = False,
) -> None:
    # settings = get_settings()
    console.print(f'🎉 Project {name} created successfully.')
    typer.Exit(0)


@prj_app.command('init')
def prj_init(
    force: bool = typer.Option(False, '--force', '-f', help='Force initialization'),
) -> None:
    # settings = get_settings()
    typer.Exit(0)


############################################################
##  Compile commands
############################################################

############################################################
##  BASE COMMANDS
############################################################


############################################################
##
############################################################


def main() -> None:
    app()


if __name__ == '__main__':
    main()
