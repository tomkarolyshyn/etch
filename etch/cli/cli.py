import datetime
import os
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

import typer
import typer.completion
from rich.pretty import Pretty
from rich.table import Table

from etch.util.install import display_status, install_all, install_tool
from etch.util.settings import AppSettings, get_settings, refresh_settings
from etch.util.util import console

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


# create sub-apps
install_app = typer.Typer()
kernel_app = typer.Typer()
compile_app = typer.Typer()
cfg_app = typer.Typer(invoke_without_command=True)
prj_app = typer.Typer()

# add sub-apps to main app
app.add_typer(install_app, name='install', help='install prerequisites for Etch')
app.add_typer(kernel_app, name='kernel', help='kernel commands')
app.add_typer(compile_app, name='compile', help='compile commands')
app.add_typer(prj_app, name='project', help='project commands')
app.add_typer(cfg_app, name='config', help='configure etch settings commands')


############################################################
##  INSTALL COMMANDS
############################################################


@install_app.command('menu')
def install_init() -> None:
    """Initialize the current directory for the etch"""
    # settings = get_settings()
    typer.Exit(0)


@install_app.command('status')
def install_status() -> None:
    """Show the status of the required tools for the etch"""
    display_status()
    typer.Exit(0)


@install_app.command('check')
def install_check() -> None:
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
## Settings command
############################################################
@cfg_app.callback()
def default_command(ctx: typer.Context) -> None:
    """Default command for the subcommand group"""
    if ctx.invoked_subcommand is None:
        cfg_list()
        # typer.echo('This is the default command!')
        # Your default logic here


@cfg_app.command('set', hidden=True)
def cfg_set(
    key: Annotated[str, typer.Argument(help='Setting key to update')],
    value: Annotated[str, typer.Argument(help='New value for the setting')],
    is_global: Annotated[bool, typer.Option('--global', '-g', help='Update global settings instead of local')] = False,
) -> None:
    """
    Update a specific setting in the configuration.
    """

    # if not update_setting(key, value, save=True):
    #     console.print(f'[red]Failed to update setting {key}[/red]')
    # else:
    #     console.print(f'[green]Setting {key} updated to {value}[/green]')


@cfg_app.command('list', hidden=True)
def cfg_list() -> None:
    """Show information about the etch environment settings"""

    info: dict[str, Any] = {}

    # Project

    # System
    os.environ['ETCH_DEBUG'] = 'True'
    settings = get_settings()
    # settings._print_config_sources()
    info['settings'] = settings.model_dump()

    # console.print(Pretty(settings.model_dump(), indent_guides=True))

    # # User authentication info
    # info['auth'] = {
    #     'email': settings.email or '',
    #     'refresh_token': settings.refresh_token or '',
    #     'has_api_key': bool(settings.api_key),
    #     'has_access_token': bool(settings.access_token),
    # }
    # console.print_json(data=info, indent=4)
    console.print(Pretty(info, indent_guides=True))

    console.print(f'Debug before: {os.environ.get("ETCH_DEBUG", "Not set")}')
    os.environ['ETCH_DEBUG'] = 'False'
    console.print(f'Debug after: {os.environ.get("ETCH_DEBUG", "Not set")}')

    settings = refresh_settings()
    settings2 = AppSettings()
    console.print(f'Settings debug: {settings2.debug}')

    info['settings_after'] = settings.model_dump()
    console.print(Pretty(info, indent_guides=True))


############################################################
##
############################################################
def main() -> None:
    app()


if __name__ == '__main__':
    main()
