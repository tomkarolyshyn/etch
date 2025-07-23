import platform
import re
import shutil
import subprocess
import tarfile
import zipfile
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path

import requests
from pydantic import Field
from pydantic.dataclasses import dataclass
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, track
from rich.table import Table

from . import tool_versions as toolver
from . import util as util
from .constants import CLOCK_SYMBOL, ERROR_SYMBOL, SUCCESS_SYMBOL, WARNING_SYMBOL, console
from .settings import AppSettings, get_settings


def _check_gitssh() -> bool:
    """Check if git ssh is configured."""
    try:
        result = subprocess.run(
            ['ssh', '-T', 'git@github.com'],  # noqa: S607
            timeout=10,
            capture_output=True,
            text=True,
        )
        # GitHub SSH test returns exit code 1 on success (by design)
        # The success message appears in stderr, not stdout
        if result.returncode == 1 and 'successfully authenticated' in result.stderr:
            console.print('✅ SSH connection to GitHub successful!')
            # console.print(f"Response: {result.stderr.strip()}")
            return True
        elif result.returncode == 255:
            console.print(f'{ERROR_SYMBOL} SSH connection failed!')
            console.print(f'Error: {result.stderr.strip()}')
            return False
        else:
            console.print(f'{WARNING_SYMBOL}  Unexpected response (exit code: {result.returncode})')
            console.print(f'stdout: {result.stdout.strip()}')
            console.print(f'stderr: {result.stderr.strip()}')
            return False

    except subprocess.TimeoutExpired:
        console.print(f'{CLOCK_SYMBOL} SSH connection timed out after 10 seconds')
        return False
    except FileNotFoundError:
        console.print(f'{ERROR_SYMBOL} SSH command not found. Please install OpenSSH client.')
        return False
    except Exception as e:
        console.print(f'{ERROR_SYMBOL} Error testing SSH connection: {e!s}')
        return False


class ToolIndex(Enum):
    """Enum for install list options.
    These should be listed in the order of installation priority.
    """

    INSTALL_DIR = 1
    COMPILERS = 2
    NINJA = 3
    LLVM = 6
    AUTHENTICATION = 8
    ALL = 9


class BuildCpu(Enum):
    """Enum-like class for CPU types (of build machine)."""

    X86_64 = 'x86_64'
    ARM64 = 'arm64'
    UNKNOWN = 'unknown'


class BuildOS(Enum):
    """Enum-like class for OS types."""

    LINUX = 'linux'
    MACOS = 'macos'
    WINDOWS = 'windows'
    UNKNOWN = 'unknown'


class ToolStatus(Enum):
    AVAILABLE = 'available'
    MISSING = 'missing'
    UNKNOWN = 'unknown'

    @classmethod
    def from_bool(cls, value: bool | None) -> 'ToolStatus':
        """Create ToolStatus from boolean value."""
        if value is None:
            return cls.UNKNOWN
        return cls.AVAILABLE if value else cls.MISSING

    def __and__(self, other: 'ToolStatus') -> 'ToolStatus':
        """Logical AND operation for ToolStatus."""
        if not isinstance(other, ToolStatus):
            return NotImplemented

        # If either is UNKNOWN, result is UNKNOWN
        if self == ToolStatus.UNKNOWN or other == ToolStatus.UNKNOWN:
            return ToolStatus.UNKNOWN
        # If either is MISSING, result is MISSING
        elif self == ToolStatus.MISSING or other == ToolStatus.MISSING:
            return ToolStatus.MISSING
        else:
            return ToolStatus.AVAILABLE

    def __or__(self, other: 'ToolStatus') -> 'ToolStatus':
        """Logical OR operation for ToolStatus."""
        if not isinstance(other, ToolStatus):
            return NotImplemented

        # If either is AVAILABLE, result is AVAILABLE
        if self == ToolStatus.AVAILABLE or other == ToolStatus.AVAILABLE:
            return ToolStatus.AVAILABLE
        # If either is UNKNOWN, result is UNKNOWN
        elif self == ToolStatus.UNKNOWN or other == ToolStatus.UNKNOWN:
            return ToolStatus.UNKNOWN
        # Both are MISSING
        else:
            return ToolStatus.MISSING


class ToolConfig(ABC):
    """Base class for tool configuration status and installation"""

    def __init__(self, index: int, name: str, ostype: BuildOS, cputype: BuildCpu) -> None:
        self.index = index
        self.name = name
        self._ostype = ostype
        self._cputype = cputype
        self._version = ''
        self._notes = ''
        self._status: ToolStatus = ToolStatus.UNKNOWN

    @abstractmethod
    def check(self) -> bool:
        """Check if the tool is installed and return its status."""
        pass

    @abstractmethod
    def install(self, force: bool = False) -> bool:
        """Install the tool if not already installed."""
        pass

    @property
    def status(self) -> ToolStatus:
        if self._status == ToolStatus.UNKNOWN:
            try:
                self._status = ToolStatus.AVAILABLE if self.check() else ToolStatus.MISSING
            except Exception:
                self._status = ToolStatus.UNKNOWN
        return self._status

    def refresh_status(self) -> ToolStatus:
        self._status = ToolStatus.UNKNOWN
        return self.status

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', status={self.status.value})"

    @property
    def version(self) -> str:
        """Get the version of the tool."""
        return self._version

    @property
    def notes(self) -> str:
        """Get the notes for the tool."""
        return self._notes


def _get_sysconfig() -> tuple[BuildOS, BuildCpu]:
    """Get the system configuration for the current machine."""

    ostype: BuildOS
    cputype: BuildCpu
    system = platform.system().lower()
    if system == 'linux':
        ostype = BuildOS.LINUX
    elif system == 'darwin':
        ostype = BuildOS.MACOS
    elif system == 'windows':
        ostype = BuildOS.WINDOWS
    else:
        ostype = BuildOS.UNKNOWN

    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        cputype = BuildCpu.X86_64
    elif 'arm' in machine or 'aarch64' in machine:
        cputype = BuildCpu.ARM64
    else:
        cputype = BuildCpu.UNKNOWN

    return ostype, cputype


def _get_xyz_version(version: str) -> str:
    """Get the X.Y.Z version number from a string."""
    match = re.search(r'\b\d+\.\d+\.\d+\b', version)
    return match.group(0) if match else ''


def _quick_merge(source: Path, dest: Path) -> None:
    """Quick merge using shutil.copytree with dirs_exist_ok"""
    shutil.copytree(
        source,
        dest,
        dirs_exist_ok=True,  # Merge instead of failing on existing dirs
    )


def _download_file(url: str, filepath: Path, description: str, force: bool = False) -> None:
    """Download file with progress bar"""
    if not force and filepath.exists():
        console.print(f'\n[yellow]Skipping {filepath} / {description} - already exists[/yellow]')
        return

    with Progress(
        TextColumn(f'[bold blue]{description}'),
        BarColumn(bar_width=40),
        '[progress.percentage]{task.percentage:>3.1f}%',
        '•',
        DownloadColumn(),
        refresh_per_second=4,
        console=console,  # Use shared console
    ) as progress:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        task_id = progress.add_task('download', total=total_size)

        with open(filepath, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                size = file.write(chunk)
                progress.update(task_id, advance=size)


#################################################################################
#  Tool Configs for install and status
#################################################################################


##########################################
class InstallDirConfig(ToolConfig):
    """Configuration for Install directory"""

    def __init__(self, ostype: BuildOS, cputype: BuildCpu) -> None:
        self.base = get_settings().install_dir.absolute()
        self.bin = self.base / 'bin'
        self.tmp = self.base / 'tmp'
        self.lib = self.base / 'lib'
        self.include = self.base / 'include'
        self.openocd = self.base / 'openocd'
        self.libexec = self.base / 'libexec'
        self.llvm = self.base / 'llvm'
        self.lib = self.base / 'lib'
        self.share = self.base / 'share'
        super().__init__(ToolIndex.INSTALL_DIR.value, 'Install Directory', ostype, cputype)

    def check(self) -> bool:
        """Check if the directories are created."""
        status: bool = True
        status &= self.base.exists()
        status &= self.bin.exists()
        status &= self.tmp.exists()
        status &= self.lib.exists()
        status &= self.include.exists()
        status &= self.openocd.exists()
        status &= self.libexec.exists()
        status &= self.llvm.exists()
        status &= self.share.exists()
        return status

    def install(self, force: bool = False) -> bool:
        self.base.mkdir(parents=True, exist_ok=True)
        self.bin.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.lib.mkdir(parents=True, exist_ok=True)
        self.include.mkdir(parents=True, exist_ok=True)
        self.openocd.mkdir(parents=True, exist_ok=True)
        self.libexec.mkdir(parents=True, exist_ok=True)
        self.llvm.mkdir(parents=True, exist_ok=True)
        self.share.mkdir(parents=True, exist_ok=True)
        console.print('Install directory created')
        return True


class NinjaConfig(ToolConfig):
    """Configuration for Ninja build system"""

    def __init__(self, ostype: BuildOS, cputype: BuildCpu) -> None:
        super().__init__(ToolIndex.NINJA.value, 'Ninja', ostype, cputype)

    def check(self) -> bool:
        """Check if NINJA is installed"""

        ok1, ver, _ = util.run_command(['ninja', '--version'])

        if self._ostype == BuildOS.WINDOWS:
            ok2, loc, _ = util.run_command(['where', 'ninja'])
        else:
            ok2, loc, _ = util.run_command(['which', 'ninja'])

        ver = _get_xyz_version(ver)
        loc = loc.strip() if loc else 'N/A'

        self._version = ver
        self._notes = loc

        return ok1 and ok2

    def install(self, force: bool = False) -> bool:
        """Setup NINJA build system"""

        # https://github.com/ninja-build/ninja/releases/tag/v1.13.0
        #     if ostype == BuildOS.MACOS and cputype == BuildCpu.ARM64:
        #         url = 'https://github.com/ninja-build/ninja/releases/download/v1.13.0/ninja-mac.zip'
        #     elif ostype == BuildOS.LINUX and cputype == BuildCpu.X86_64:
        #         url = 'https://github.com/ninja-build/ninja/releases/download/v1.13.0/ninja-linux.zip'
        #     else:
        #         raise ValueError(f'Unsupported OS type: {self._ostype} for CPU type: {self._cputype}')
        #         return

        #     if get_install_dirs().ninja.exists():
        #         console.print('NINJA already installed, skipping setup')
        #         return

        console.print('Ninja is currently setup via pip install ninja')
        return True


##########################################


class LLVMConfig(ToolConfig):
    """Configuration for LLVM"""

    def __init__(self, ostype: BuildOS, cputype: BuildCpu) -> None:
        super().__init__(ToolIndex.LLVM.value, 'LLVM', ostype, cputype)

    def check(self) -> bool:
        """Check if LLVM is installed."""
        version = 'N/A'
        location = 'N/A'
        found = False
        try:
            result = subprocess.run(
                ['clang', '--version'],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                found = True
                version_match = re.search(r'clang version (\d+\.\d+\.\d+)', result.stdout)
                if version_match:
                    version = version_match.group(1)

                    # Extract installation directory
                install_match = re.search(r'InstalledDir:\s+(.+)', result.stdout)
                if install_match:
                    location = install_match.group(1)
        except (subprocess.SubprocessError, FileNotFoundError):
            self._version = '--'
            self._notes = '--'
            return False

        self._version = version
        self._notes = location
        return found

    def _get_fname(self) -> str:
        # # linux    https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.7/LLVM-20.1.7-Linux-X64.tar.xz
        # # macos    https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.7/LLVM-20.1.7-macOS-ARM64.tar.xz
        # https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.7/LLVM-20.1.7-Linux-ARM64.tar.xz

        fname = f'LLVM-{toolver.LLVM_VERSION}-'
        match self._ostype:
            case BuildOS.LINUX:
                fname += 'Linux-'
                if self._cputype == BuildCpu.X86_64:
                    fname += 'X64.tar.xz'
                elif self._cputype == BuildCpu.ARM64:
                    fname += 'ARM64.tar.xz'
                else:
                    fname += 'Unknown.tar.xz'
            case BuildOS.MACOS:
                fname += 'macOS-'
                if self._cputype == BuildCpu.ARM64:
                    fname += 'ARM64.tar.xz'
                elif self._cputype == BuildCpu.X86_64:
                    fname += 'X64.tar.xz'
                else:
                    raise ValueError(f'Unsupported CPU type: {self._cputype} for MacOS')
            case BuildOS.WINDOWS:
                # fname += f"LLVM-20.1.7-win64.exe  "
                raise NotImplementedError('Windows support for LLVM is not implemented yet.')
            case _:
                raise ValueError(f'Unsupported OS type: {self._ostype}')

        return fname

    def install(self, force: bool = False) -> None:
        """Install LLVM"""
        console.print('[yellow]LLVM Install is not supported yet, use the setup_scripts to install[/yellow]')

        return False

        # if self._ostype not in BuildOS.__dict__.values():
        #     raise ValueError(f'Unsupported OS type: {self._ostype}')

        # if self._cputype not in BuildCpu.__dict__.values():
        #     raise ValueError(f'Unsupported CPU type: {cputype}')

        # fname = self._get_fname()
        # if get_install_dirs().llvm.exists():
        #     print(f'LLVM directory {get_install_dirs().llvm} already exists, skipping setup.')
        #     return

        # # download
        # if not (get_install_dirs().tmp / fname).exists():
        #     url = f'https://github.com/llvm/llvm-project/releases/download/llvmorg-{toolver.LLVM_VERSION}/{fname}'
        #     print(f'Downloading {url}...')
        #     response = requests.get(url, stream=True, timeout=300)
        #     response.raise_for_status()
        #     with open(get_install_dirs().tmp / fname, 'wb') as f:
        #         for chunk in response.iter_content(chunk_size=8192):
        #             f.write(chunk)
        # else:
        #     print(f'File {fname} already exists in {get_install_dirs().tmp}, skipping download.')

        # # extract
        # print(f'Extracting {fname}...')
        # if self._ostype in (BuildOS.LINUX, BuildOS.MACOS):
        #     with tarfile.open(get_install_dirs().tmp / fname, 'r:xz') as tar:
        #         tar.extractall(get_install_dirs().tmp, filter='data')
        # # elif ostype == BuildOS.WINDOWS:
        # #     with zipfile.ZipFile(get_tmp_dir() / fname, 'r') as zip_ref:
        # #         zip_ref.extractall(get_tmp_dir(), filter='data')
        # else:
        #     raise ValueError(f'Unsupported OS type for extraction: {self._ostype}')

        # tmpdir = get_install_dirs().tmp / fname.replace('.tar.xz', '')
        # print(f'moving {tmpdir} to {get_install_dirs().llvm}')

        # shutil.move(get_install_dirs().tmp / fname.replace('.tar.xz', ''), get_install_dirs().llvm)

        # print('Creating symlinks for LLVM tools...')
        # # update links
        # # llvm_ver_major = toolver.LLVM_VERSION.split('.')[0]
        # _create_symlink(get_install_dirs().llvm / 'bin/llvm-config', get_install_dirs().bin / 'llvm-config')
        # _create_symlink(get_install_dirs().llvm / 'bin/clang', get_install_dirs().bin / 'clang')
        # _create_symlink(get_install_dirs().llvm / 'bin/clangd', get_install_dirs().bin / 'clangd')
        # _create_symlink(get_install_dirs().llvm / 'bin/clang++', get_install_dirs().bin / 'clang++')
        # _create_symlink(get_install_dirs().llvm / 'bin/lld', get_install_dirs().bin / 'lld')
        # _create_symlink(get_install_dirs().llvm / 'bin/lldb', get_install_dirs().bin / 'lldb')
        # _create_symlink(
        #     get_install_dirs().llvm / 'bin/intercept-build', get_install_dirs().bin / 'intercept-build'
        # )
        # _create_symlink(get_install_dirs().llvm / 'bin/scan-build', get_install_dirs().bin / 'scan-build')


##########################################
class CompilerConfig(ToolConfig):
    """Configuration for Compilers"""

    def __init__(self, ostype: BuildOS, cputype: BuildCpu) -> None:
        self.compiler_list = {
            'arm32': ['', 'arm-none-eabi'],
            'arm64': ['', 'aarch64-none-elf'],
            'riscv': ['', 'riscv64-unknown-elf'],
        }
        super().__init__(ToolIndex.COMPILERS.value, 'ARM Compilers', ostype, cputype)

    def check(self) -> bool:
        """Check if the compilers are installed."""

        """Check if compilers are installed."""

        if not (get_install_dirs().bin / 'arm-none-eabi-gcc').exists():
            return False

        ok1, version_str, _ = util.run_command(['arm-none-eabi-gcc', '--version'])
        ok2, location, _ = util.run_command(['which', 'arm-none-eabi-gcc'])

        self._version = 'N/A'
        pattern = r'(\d+\.\d+\.\d+)\s+(\d{8})'
        match = re.search(pattern, version_str)
        if match:
            self._version = match.group(1)
            # date = match.group(2)

        self._notes = location.strip()
        # console.print(f'good = {ok1 and ok2} Compiler version: {self._version}, location: {self._notes}')
        return ok1 and ok2

    def install(self, force: bool = False) -> None:
        """Setup ARM compilers.
        https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
        """
        if self._ostype == BuildOS.MACOS and self._cputype == BuildCpu.ARM64:
            self.compiler_list['arm32'][0] = (
                'https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-darwin-arm64-arm-none-eabi.tar.xz'
            )
            self.compiler_list['arm64'][0] = (
                'https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-darwin-arm64-aarch64-none-elf.tar.xz'
            )
            self.compiler_list['riscv'][0] = ''
        elif self._ostype == BuildOS.LINUX and self._cputype == BuildCpu.X86_64:
            self.compiler_list['arm32'][0] = (
                'https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi.tar.xz'
            )
            self.compiler_list['arm64'][0] = (
                'https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf.tar.xz'
            )
            self.compiler_list['riscv'][0] = ''
        else:
            # return False
            raise ValueError(f'Unsupported OS type: {self._ostype} for CPU type: {self._cputype}')

        filelist = []

        for arch, (url, name) in self.compiler_list.items():
            if not url:
                # console.print(f"Skipping {arch} - no URL")
                continue

            filename = url.split('/')[-1]
            filepath = get_install_dirs().tmp / filename
            filelist.append((filepath, name))

            if filepath.exists():
                if not force:
                    console.print(f'[yellow]Skipping {arch} : {name} - {filename} already exists[/yellow]')
                    continue
                else:
                    console.print(f'[yellow]Forcing re-download of {arch} : {name}[/yellow]')
                    filepath.unlink(missing_ok=True)

            try:
                _download_file(url, filepath, f'{arch} : {name}')
                console.print(f'[green]✓ {arch} : {name} downloaded successfully[/green]')
            except Exception as e:
                console.print(f'[red]✗ {arch} : {name}  failed: {e}[/red]')

        # extract
        for filepath, name in filelist:
            print(f'filepath: {filepath}')
            fldr_extract = filepath.parent / filepath.name.replace('.tar.xz', '')

            if fldr_extract.exists():
                console.print(f'[yellow]Skipping {name} already installed[/yellow]')
                continue

            console.print(f'Installing {name} ...')
            with tarfile.open(filepath, 'r:xz') as tar:
                tar.extractall(get_install_dirs().tmp, filter='data')

            _quick_merge(fldr_extract / 'bin', get_install_dirs().bin)
            _quick_merge(fldr_extract / 'lib', get_install_dirs().lib)
            _quick_merge(fldr_extract / 'include', get_install_dirs().include)
            _quick_merge(fldr_extract / 'share', get_install_dirs().share)
            _quick_merge(fldr_extract / 'libexec', get_install_dirs().libexec)
            shutil.move(fldr_extract / name, get_install_dirs().base / name)
        return True


##########################################


def check_auth() -> bool:
    """check token/auth status with server"""
    status = False

    return status


OS_TYPE, CPU_TYPE = _get_sysconfig()
# global list
ToolList = [
    InstallDirConfig(OS_TYPE, CPU_TYPE),
    NinjaConfig(OS_TYPE, CPU_TYPE),
    CompilerConfig(OS_TYPE, CPU_TYPE),
    LLVMConfig(OS_TYPE, CPU_TYPE),
]
ToolList.sort(key=lambda x: x.index)  # Sort by index for consistent order


def get_install_dirs() -> InstallDirConfig:
    """Get the installation directories."""
    return ToolList[ToolIndex.INSTALL_DIR.value - 1]  # InstallDirConfig is the first item in ToolList


#####################
## external methods for CLI


def _get_status_str(status: ToolStatus | bool | None) -> str:
    """Get the status string for a tool."""
    if status is None or status == ToolStatus.UNKNOWN:
        return '[yellow]❓[/yellow]'
    elif status == ToolStatus.AVAILABLE or status is True:
        return '[green]✅[/green]'
    else:
        return '[red]❌[/red]'


def display_status() -> None:
    """Display the status of the etch setup."""

    table = Table(title='Dependencies install status')
    table.add_column('#', justify='left', width=4)
    table.add_column('Name', justify='left', width=20)
    table.add_column('Status', justify='center', width=10)
    table.add_column('Version', justify='center', width=20)
    table.add_column('Notes', justify='left', width=60)

    status_all = ToolStatus.AVAILABLE
    for tool in ToolList:
        status_str = _get_status_str(tool.status)
        table.add_row(str(tool.index), tool.name, status_str, tool.version, tool.notes)
        status_all = tool.status and status_all  # Combine statuses
    # print the table

    auth_status = ToolStatus.from_bool(check_auth())
    status_all = status_all and auth_status

    table.add_row(str(ToolIndex.AUTHENTICATION.value), 'Authentication', _get_status_str(auth_status), '--', '--')

    table.add_row(str(ToolIndex.ALL.value), 'All', _get_status_str(status_all), '--', '--')
    console.print(table)


def install_all() -> None:
    """Run all setup steps"""

    install_tool(ToolIndex.ALL)


def install_tool(selection: int | ToolIndex, showstatus: bool = True) -> bool:
    """Install a specific tool by index or ToolIndex enum."""

    install_list: list[ToolConfig] = []

    if isinstance(selection, int):
        if selection == -1 or selection == ToolIndex.ALL.value:
            install_list = ToolList
        elif 0 <= selection < len(ToolList):
            install_list = [ToolList[selection]]
        else:
            console.print(f'[red]Invalid selection index: {selection}[/red]')
            return False
    elif isinstance(selection, ToolIndex):
        if selection == ToolIndex.ALL:  # noqa :SIM108
            install_list = ToolList
        else:
            install_list = [ToolList[selection.value]]
    else:
        console.print(f'[red]Invalid selection: {selection}[/red]')

        return False

    # setup_llvm(ostype=ostype, cputype=cputype)
    for tool in install_list:
        console.print(f'Setting up {tool.name}...')
        try:
            tool.install()
            console.print(f'[green]✓[/green] {tool.name} setup complete')
        except Exception as e:
            console.print(f'[red]✗[/red] {tool.name} setup failed: {e}')
            continue
    console.print('Setup complete')
    if showstatus:
        display_status()
    return True
