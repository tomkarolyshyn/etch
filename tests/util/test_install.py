from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from etch.util.install import (
    BuildCpu,
    BuildOS,
    CompilerConfig,
    InstallDirConfig,
    LLVMConfig,
    NinjaConfig,
    ToolConfig,
    ToolIndex,
    ToolList,
    ToolStatus,
    _get_sysconfig,
    display_status,
    get_install_dirs,
    install_tool,
)


class TestToolVersionsImport:
    """Test that tool_versions module imports correctly."""

    def test_tool_versions_import_succeeds(self) -> None:
        """Test that tool_versions module can be imported successfully."""
        from etch.util import tool_versions

        # Test that version constants are accessible
        assert hasattr(tool_versions, 'LLVM_VERSION')
        assert hasattr(tool_versions, 'ARM_GCC_VERSION')
        assert hasattr(tool_versions, 'NINJA_VERSION')
        assert hasattr(tool_versions, 'OPENOCD_VERSION')

        # Test that versions are strings
        assert isinstance(tool_versions.LLVM_VERSION, str)
        assert isinstance(tool_versions.ARM_GCC_VERSION, str)
        assert isinstance(tool_versions.NINJA_VERSION, str)
        assert isinstance(tool_versions.OPENOCD_VERSION, str)


class TestEnums:
    """Test enum classes."""

    def test_build_os_enum(self) -> None:
        """Test BuildOS enum values."""
        assert BuildOS.LINUX.value == 'linux'
        assert BuildOS.MACOS.value == 'macos'
        assert BuildOS.WINDOWS.value == 'windows'
        assert BuildOS.UNKNOWN.value == 'unknown'

    def test_build_cpu_enum(self) -> None:
        """Test BuildCpu enum values."""
        assert BuildCpu.X86_64.value == 'x86_64'
        assert BuildCpu.ARM64.value == 'arm64'
        assert BuildCpu.UNKNOWN.value == 'unknown'

    def test_tool_index_enum(self) -> None:
        """Test ToolIndex enum values."""
        assert ToolIndex.INSTALL_DIR.value == 1
        assert ToolIndex.COMPILERS.value == 2
        assert ToolIndex.NINJA.value == 3
        assert ToolIndex.LLVM.value == 6
        assert ToolIndex.AUTHENTICATION.value == 8
        assert ToolIndex.ALL.value == 9


class TestToolStatus:
    """Test ToolStatus enum and operations."""

    def test_from_bool_available(self) -> None:
        """Test ToolStatus.from_bool with True."""
        status = ToolStatus.from_bool(True)
        assert status == ToolStatus.AVAILABLE

    def test_from_bool_missing(self) -> None:
        """Test ToolStatus.from_bool with False."""
        status = ToolStatus.from_bool(False)
        assert status == ToolStatus.MISSING

    def test_from_bool_unknown(self) -> None:
        """Test ToolStatus.from_bool with None."""
        status = ToolStatus.from_bool(None)
        assert status == ToolStatus.UNKNOWN

    def test_and_operation(self) -> None:
        """Test logical AND operation for ToolStatus."""
        # AVAILABLE & AVAILABLE = AVAILABLE
        result = ToolStatus.AVAILABLE & ToolStatus.AVAILABLE
        assert result == ToolStatus.AVAILABLE

        # AVAILABLE & MISSING = MISSING
        result = ToolStatus.AVAILABLE & ToolStatus.MISSING
        assert result == ToolStatus.MISSING

        # AVAILABLE & UNKNOWN = UNKNOWN
        result = ToolStatus.AVAILABLE & ToolStatus.UNKNOWN
        assert result == ToolStatus.UNKNOWN

    def test_or_operation(self) -> None:
        """Test logical OR operation for ToolStatus."""
        # AVAILABLE | MISSING = AVAILABLE
        result = ToolStatus.AVAILABLE | ToolStatus.MISSING
        assert result == ToolStatus.AVAILABLE

        # MISSING | MISSING = MISSING
        result = ToolStatus.MISSING | ToolStatus.MISSING
        assert result == ToolStatus.MISSING

        # MISSING | UNKNOWN = UNKNOWN
        result = ToolStatus.MISSING | ToolStatus.UNKNOWN
        assert result == ToolStatus.UNKNOWN


class TestGetSysconfig:
    """Test system configuration detection."""

    @patch('platform.system')
    @patch('platform.machine')
    def test_linux_x86_64(self, mock_machine, mock_system):
        """Test detection of Linux x86_64."""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'x86_64'

        ostype, cputype = _get_sysconfig()
        assert ostype == BuildOS.LINUX
        assert cputype == BuildCpu.X86_64

    @patch('platform.system')
    @patch('platform.machine')
    def test_macos_arm64(self, mock_machine, mock_system):
        """Test detection of macOS ARM64."""
        mock_system.return_value = 'Darwin'
        mock_machine.return_value = 'arm64'

        ostype, cputype = _get_sysconfig()
        assert ostype == BuildOS.MACOS
        assert cputype == BuildCpu.ARM64

    @patch('platform.system')
    @patch('platform.machine')
    def test_unknown_system(self, mock_machine, mock_system):
        """Test detection of unknown system."""
        mock_system.return_value = 'Unknown'
        mock_machine.return_value = 'unknown'

        ostype, cputype = _get_sysconfig()
        assert ostype == BuildOS.UNKNOWN
        assert cputype == BuildCpu.UNKNOWN


class TestInstallDirConfig:
    """Test InstallDirConfig class."""

    @patch('etch.util.install.get_settings')
    def test_init_creates_paths(self, mock_get_settings):
        """Test that InstallDirConfig initializes paths correctly."""
        mock_settings = Mock()
        mock_settings.install_dir.absolute.return_value = Path('/test/install')
        mock_get_settings.return_value = mock_settings

        config = InstallDirConfig(BuildOS.LINUX, BuildCpu.X86_64)

        assert config.base == Path('/test/install')
        assert config.bin == Path('/test/install/bin')
        assert config.tmp == Path('/test/install/tmp')
        assert config.llvm == Path('/test/install/llvm')

    @patch('etch.util.install.get_settings')
    def test_check_all_directories_exist(self, mock_get_settings):
        """Test check method when all directories exist."""
        mock_settings = Mock()
        # Create a proper Path mock that supports / operator
        mock_base = Path('/test/install')
        mock_settings.install_dir.absolute.return_value = mock_base
        mock_get_settings.return_value = mock_settings

        config = InstallDirConfig(BuildOS.LINUX, BuildCpu.X86_64)

        # Mock all path exists() methods to return True
        with patch.object(Path, 'exists', return_value=True):
            result = config.check()
            assert result is True


class TestNinjaConfig:
    """Test NinjaConfig class."""

    def test_init(self) -> None:
        """Test NinjaConfig initialization."""
        config = NinjaConfig(BuildOS.LINUX, BuildCpu.X86_64)
        assert config.name == 'Ninja'
        assert config.index == ToolIndex.NINJA.value

    @patch('etch.util.install.util.run_command')
    def test_check_ninja_available(self, mock_run_command: Mock) -> None:
        """Test check method when ninja is available."""
        mock_run_command.side_effect = [
            (True, '1.13.0', ''),  # ninja --version
            (True, '/usr/bin/ninja', ''),  # which ninja
        ]

        config = NinjaConfig(BuildOS.LINUX, BuildCpu.X86_64)
        result = config.check()

        assert result is True
        assert config.version == '1.13.0'
        assert config.notes == '/usr/bin/ninja'

    def test_install_returns_true(self) -> None:
        """Test install method returns True (pip install ninja)."""
        config = NinjaConfig(BuildOS.LINUX, BuildCpu.X86_64)
        result = config.install()
        assert result is True


class TestLLVMConfig:
    """Test LLVMConfig class."""

    def test_init(self) -> None:
        """Test LLVMConfig initialization."""
        config = LLVMConfig(BuildOS.LINUX, BuildCpu.X86_64)
        assert config.name == 'LLVM'
        assert config.index == ToolIndex.LLVM.value

    @patch('subprocess.run')
    def test_check_llvm_available(self, mock_run: Mock) -> None:
        """Test check method when LLVM is available."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'clang version 20.1.7\nInstalledDir: /usr/bin'
        mock_run.return_value = mock_result

        config = LLVMConfig(BuildOS.LINUX, BuildCpu.X86_64)
        result = config.check()

        assert result is True
        assert config.version == '20.1.7'
        assert config.notes == '/usr/bin'

    def test_get_fname_linux_x86_64(self) -> None:
        """Test _get_fname method for Linux x86_64."""
        config = LLVMConfig(BuildOS.LINUX, BuildCpu.X86_64)
        fname = config._get_fname()
        assert fname.startswith('LLVM-')
        assert 'Linux-X64.tar.xz' in fname

    def test_get_fname_macos_arm64(self) -> None:
        """Test _get_fname method for macOS ARM64."""
        config = LLVMConfig(BuildOS.MACOS, BuildCpu.ARM64)
        fname = config._get_fname()
        assert fname.startswith('LLVM-')
        assert 'macOS-ARM64.tar.xz' in fname

    def test_get_fname_windows_raises_error(self):
        """Test _get_fname method raises error for Windows."""
        config = LLVMConfig(BuildOS.WINDOWS, BuildCpu.X86_64)
        with pytest.raises(NotImplementedError):
            config._get_fname()

    def test_install_returns_false(self):
        """Test install method returns False (not implemented)."""
        config = LLVMConfig(BuildOS.LINUX, BuildCpu.X86_64)
        result = config.install()
        assert result is False


# class TestCompilerConfig:
#     """Test CompilerConfig class."""

#     def test_init(self):
#         """Test CompilerConfig initialization."""
#         config = CompilerConfig(BuildOS.LINUX, BuildCpu.X86_64)
#         assert config.name == 'ARM Compilers'
#         assert config.index == ToolIndex.COMPILERS.value
#         assert 'arm32' in config.compiler_list
#         assert 'arm64' in config.compiler_list
#         assert 'riscv' in config.compiler_list

#     @patch('etch.util.install.get_install_dirs')
#     @patch('etch.util.install.util.run_command')
#     def test_check_compiler_available(self, mock_run_command, mock_get_install_dirs):
#         """Test check method when compiler is available."""
#         # Mock install dirs
#         mock_dirs = Mock()
#         mock_dirs.bin = Path('/test/bin')
#         mock_get_install_dirs.return_value = mock_dirs

#         # Mock file exists
#         with patch.object(Path, 'exists', return_value=True):
#             mock_run_command.side_effect = [
#                 (True, 'arm-none-eabi-gcc version 13.3.1 20240614', ''),  # --version
#                 (True, '/test/bin/arm-none-eabi-gcc', ''),  # which
#             ]

#             config = CompilerConfig(BuildOS.LINUX, BuildCpu.X86_64)
#             result = config.check()

#             assert result is True
#             assert config.version == '13.3.1'
#             assert config.notes == '/test/bin/arm-none-eabi-gcc'


class TestUtilityFunctions:
    """Test utility functions."""

    def test_get_install_dirs_returns_install_dir_config(self) -> None:
        """Test get_install_dirs returns InstallDirConfig."""
        dirs = get_install_dirs()
        assert isinstance(dirs, InstallDirConfig)

    @patch('etch.util.install.console.print')
    def test_display_status_prints_table(self, mock_print: Mock) -> None:
        """Test display_status prints status table."""
        display_status()
        # Verify that console.print was called (table output)
        assert mock_print.called

    @patch('etch.util.install.console.print')
    @pytest.mark.skip(reason='Skipping install_tool tests for now')
    def test_install_tool_all(self, mock_print: Mock) -> None:
        """Test install_tool with ALL selection."""
        result = install_tool(ToolIndex.ALL, showstatus=False)
        assert result is True
        assert mock_print.called

    @patch('etch.util.install.console.print')
    @pytest.mark.skip(reason='Skipping install_tool tests for now')
    def test_install_tool_specific_index(self, mock_print: Mock) -> None:
        """Test install_tool with specific index."""
        result = install_tool(ToolIndex.INSTALL_DIR, showstatus=False)
        assert result is True
        assert mock_print.called

    def test_install_tool_invalid_selection(self) -> None:
        """Test install_tool with invalid selection."""
        with patch('etch.util.install.console.print') as mock_print:
            result = install_tool(999, showstatus=False)
            assert result is False
            mock_print.assert_called_with('[red]Invalid selection index: 999[/red]')


class TestToolList:
    """Test ToolList global variable."""

    def test_tool_list_contains_expected_tools(self):
        """Test that ToolList contains expected tool configurations."""
        assert len(ToolList) == 4

        # Check that all expected tool types are present
        tool_types = [type(tool).__name__ for tool in ToolList]
        assert 'InstallDirConfig' in tool_types
        assert 'NinjaConfig' in tool_types
        assert 'CompilerConfig' in tool_types
        assert 'LLVMConfig' in tool_types

    def test_tool_list_is_sorted_by_index(self):
        """Test that ToolList is sorted by index."""
        indices = [tool.index for tool in ToolList]
        assert indices == sorted(indices)
