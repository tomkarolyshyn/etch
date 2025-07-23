import enum
import io
import json
import shutil
import sys
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from shlex import split
from typing import Any, NoReturn, Self, TextIO

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from etch.util.constants import console


class RtosTypes(str, enum.Enum):
    """
    Enum for RTOS types.
    """

    baremetal = 'BareMetal'
    FREE_RTOS = 'FreeRTOS'
    ZEPHYR = 'Zephyr'
    VxWorks = 'VxWorks'


class ProjectTemplates(str, enum.Enum):
    empty = 'empty'
    hello = 'hello'
    dsp = 'dsp'


DEFAULT_RTOS = RtosTypes.baremetal
DEFAULT_TEMPLATE = ProjectTemplates.empty

DEFAULT_COMPILER_OPTIONS: list[str] = ['Wall', 'Wextra', '-O1']
DEFAULT_COMPILE_DEFINITIONS: list[str] = []
DEFAULT_LINK_OPTIONS: list[str] = []
DEFAULT_LINK_LIBS: list[str] = ['c']


class ProjectConfig(BaseModel):
    """
    Per-project configuration singleton
    """

    fileid: str = Field(frozen=True, default='ETCH001', description='Idenftifies this as a ETCH project')
    name: str = Field(frozen=True, default='project1', description='Name of the project')
    project_uuid: str = Field(
        frozen=True,  # This should not change after creation
        default_factory=lambda: str(uuid.uuid4()),
        description='Unique identifier for the project (For server use)',
    )

    project_path: Path = Field(
        frozen=True, default_factory=lambda: Path('.'), description='Path to the project directory'
    )

    model_config = ConfigDict(
        alias_generator=lambda field_name: field_name.replace('_', '-'),
        populate_by_name=True,  # Allows both field name and alias
    )

    rtos: RtosTypes = Field(default=DEFAULT_RTOS)
    template: ProjectTemplates = Field(default=DEFAULT_TEMPLATE)

    source_files: list[Path] = Field(
        default_factory=list, description='List of source files in the project, used for hardware generation'
    )
    include_dirs: list[Path] = Field(default_factory=list, description='List of include directories for the project')
    libraries: list[str] = Field(default_factory=list, description='List of Xilinx libraries to link against')
    compiler_options: list[str] = Field(
        default_factory=lambda: DEFAULT_COMPILER_OPTIONS.copy(), description='List of compiler options for the project'
    )
    compile_definitions: list[str] = Field(
        default_factory=lambda: DEFAULT_COMPILE_DEFINITIONS.copy(),
        description='List of preprocessor definitions for the project',
    )
    link_options: list[str] = Field(
        default_factory=lambda: DEFAULT_LINK_OPTIONS.copy(), description='List of linker options for the project'
    )
    link_libs: list[str] = Field(
        default_factory=lambda: DEFAULT_LINK_LIBS.copy(), description='List of libraries to link against'
    )
    functions: list[str] = Field(
        default_factory=list, description='List of kernel functions in the project, used for hardware generation'
    )

    @field_validator('fileid')
    @classmethod
    def validate_fileid(cls, v: str) -> str:
        if v != 'ETCH001':
            msg = f"Expected fileid 'ETCH001', got '{v}'"
            raise ValueError(msg)
        return v

    def _cleanup(self) -> None:
        """Cleanup method to remove any temporary files or directories."""
        if self.work_path.exists():
            shutil.rmtree(self.work_path)
        if self.project_config_path.exists():
            self.project_config_path.unlink()

        path = self.project_path / f'{self.name}.yaml'
        filename = Path(path).resolve()
        if filename.exists():
            filename.unlink()

    @classmethod
    def create(cls, root: Path = Path('.'), name: str = 'project1', force: bool = False) -> 'ProjectConfig':
        root = root.resolve()

        root.mkdir(parents=True, exist_ok=True)
        filepath = root / f'{name}.yaml'

        if filepath.exists() and not force:
            raise FileExistsError(f"Project '{name}' already exists at {filepath}")

        project = ProjectConfig(
            project_path=root.resolve(),
            name=name,
            project_uuid=str(uuid.uuid4()),
        )

        project.work_path.mkdir(exist_ok=True)
        project.hw_path.mkdir(exist_ok=True)
        project.src_path.mkdir(exist_ok=True)
        project.functions_base_path.mkdir(exist_ok=True)
        project.save(filepath)

        return project

    @property
    def project_config_path(self) -> Path:
        return self.project_path / f'{self.name}.yaml'

    @property
    def work_path(self) -> Path:
        return self.project_path / '.etch'

    @property
    def functions_base_path(self) -> Path:
        return self.work_path / 'functions'

    @property
    def src_path(self) -> Path:
        return self.project_path / 'src'

    @property
    def build_path(self) -> Path:
        """Return the build directory path."""
        return self.project_path / 'build'

    @property
    def hw_path(self) -> Path:
        """Return the hardware directory path."""
        return self.project_path / 'hw'

    #### Save methods ####
    def _get_field_groups(self) -> dict[str, list]:
        """Group fields logically"""
        return {
            'Project': ['vendor', 'name', 'project-uuid', 'template'],
            'Software': [
                'rtos',
                'source-files',
                'include-dirs',
                'libraries',
                'compiler-options',
                'compile-definitions',
                'link-options',
                'link-libs',
            ],
            'Functions': ['functions'],
            # 'Hardware': ['hardware']
        }

    def _write_header(self, f: io.TextIOWrapper) -> None:
        """Write file header"""
        border = '#' + '=' * 77
        f.write(f'{border}\n')
        f.write(f'# {self.__class__.__name__} Configuration\n')
        f.write(f'{border}\n')
        f.write(f'# Generated: {datetime.now().strftime("%A, %B %d, %Y at %I:%M:%S %p")}\n')
        f.write(f'# Project: {getattr(self, "name", "Unknown")}\n')
        f.write('#\n')
        f.write(f'{border}\n\n')

    def _write_yaml_with_descriptions(self, f: io.TextIOWrapper) -> None:
        """Write YAML with field descriptions as comments"""
        data = self.model_dump(mode='json', exclude_none=True, by_alias=True)
        field_groups = self._get_field_groups()

        for group_name, fields in field_groups.items():
            if any(field in data for field in fields):
                f.write(f'# {group_name}\n')
                f.write(f'# {"-" * len(group_name)}\n')

                for field_name in fields:
                    if field_name in data:
                        self._write_field_with_description(f, field_name, data[field_name])

                f.write('\n')

    def _write_field_with_description(self, f: io.TextIOWrapper, field_name: str, value: Any) -> None:
        """Write field with its description as comment"""
        # Get field info from model
        # field_info = self.model_fields.get(field_name)

        comment = ''
        # field_info = type(self).model_fields.get(field_name)
        # if field_info and field_info.description:
        #     comment = f'# {field_info.description}'

        if isinstance(value, dict | list) and value:
            f.write(f'{field_name}:\n')
            # f.write(f'{comment}\n')
            yaml_str = yaml.safe_dump(value, default_flow_style=False, indent=2, sort_keys=False)
            for line in yaml_str.strip().split('\n'):
                f.write(f'  {line}\n')
            # f.write('\n')
        else:
            yaml_str = yaml.safe_dump({field_name: value}, default_flow_style=False, sort_keys=False)
            f.write(yaml_str.rstrip())
            f.write(f'  {comment}\n')

    def save(self, path: Path | None = None) -> None:
        """Save the configuration to a YAML file."""

        header = '# ETCH Project configuration file\n'
        header += f'# Last Modified on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'

        if path is None:  # noqa : SIM108
            filename = self.project_config_path
        else:
            filename = Path(path).resolve()

        with open(filename, 'w', encoding='utf-8') as f:
            self._write_header(f)
            # Ensure functions list is not sorted before writing
            # (YAML and Python lists preserve order by default)
            self._write_yaml_with_descriptions(f)
