import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from etch.cli.cli import app, config_app, install_completion, main, prj_app, version_callback
from etch.util.settings import AppSettings, SettingsManager


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def clean_settings() -> Generator[None, None, None]:
    """Clean up SettingsManager singleton between tests."""
    SettingsManager._instance = None
    yield
    SettingsManager._instance = None


@pytest.fixture
def mock_settings() -> AppSettings:
    """Create mock settings for testing."""
    return AppSettings(
        debug=True,
        log_level='DEBUG',
        api_host='testhost',
        api_port=9000,
        enable_caching=False,
    )


class TestMainApp:
    """Test the main application and callbacks."""

    def test_version_callback_shows_version(self, runner: CliRunner) -> None:
        """Test that version callback shows version and exits."""
        with pytest.raises(typer.Exit):
            version_callback(True)

    def test_version_flag(self, runner: CliRunner) -> None:
        """Test --version flag shows version."""
        result = runner.invoke(app, ['--version'])
        assert result.exit_code == 0
        assert 'etch' in result.stdout

    def test_help_flag(self, runner: CliRunner) -> None:
        """Test --help flag shows help."""
        result = runner.invoke(app, ['--help'])
        assert result.exit_code == 0
        assert 'Usage:' in result.stdout

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        """Test that no arguments shows help."""
        result = runner.invoke(app, [])
        assert result.exit_code == 2
        assert 'Usage:' in result.stdout

    def test_main_function(self) -> None:
        """Test the main function exists and can be called."""
        # Just test it exists and is callable
        assert callable(main)


class TestConfigCommands:
    """Test configuration commands."""

    def test_config_list_command(self, runner: CliRunner, clean_settings: None) -> None:
        """Test config list command shows settings table."""
        result = runner.invoke(config_app, ['list'])
        assert result.exit_code == 0
        assert 'App Configuration Settings' in result.stdout
        assert 'Setting' in result.stdout
        assert 'Value' in result.stdout
        assert 'Type' in result.stdout

    def test_config_list_with_mock_settings(self, runner: CliRunner, mock_settings: AppSettings) -> None:
        """Test config list with specific settings."""
        with patch('etch.cli.cli.get_settings', return_value=mock_settings):
            result = runner.invoke(config_app, ['list'])
            assert result.exit_code == 0
            assert 'testhost' in result.stdout
            assert '9000' in result.stdout

    def test_config_init_command(self, runner: CliRunner) -> None:
        """Test config init command."""
        result = runner.invoke(config_app, ['init'])
        assert result.exit_code == 0

    def test_config_install_command(self, runner: CliRunner) -> None:
        """Test config install command."""
        result = runner.invoke(config_app, ['install'])
        assert result.exit_code == 0

    def test_config_check_command(self, runner: CliRunner) -> None:
        """Test config check command."""
        result = runner.invoke(config_app, ['check'])
        assert result.exit_code == 0


class TestProjectCommands:
    """Test project commands."""

    def test_prj_create_command(self, runner: CliRunner) -> None:
        """Test project create command with required arguments."""
        result = runner.invoke(prj_app, ['create', 'test-project', '--template', 'test', '--board', 'test-board'])
        assert result.exit_code == 0

    def test_prj_create_with_force(self, runner: CliRunner) -> None:
        """Test project create with force flag."""
        result = runner.invoke(
            prj_app, ['create', 'test-project', '--template', 'test', '--board', 'test-board', '--force']
        )
        assert result.exit_code == 0

    # def test_prj_create_missing_name(self, runner: CliRunner) -> None:
    #     """Test project create without required name argument."""
    #     result = runner.invoke(prj_app, ['create', '--template', 'test', '--board', 'test-board'])
    #     assert result.exit_code != 0
    #     assert 'Missing argument' in result.stdout

    # def test_prj_create_missing_template(self, runner: CliRunner) -> None:
    #     """Test project create without required template argument."""
    #     result = runner.invoke(prj_app, ['create', 'test-project', '--board', 'test-board'])
    #     assert result.exit_code != 0
    #     assert 'Missing argument' in result.stdout


# class TestCompletionCommand:
#     """Test completion installation command."""

#     def test_install_completion_auto_detect(self, runner: CliRunner) -> None:
#         """Test completion installation with auto-detect."""
#         with patch.dict(os.environ, {'SHELL': '/bin/bash'}):
#             with patch('pathlib.Path.write_text') as mock_write:
#                 result = runner.invoke(app, ['--install-completion'])
#                 assert result.exit_code == 0
#                 assert 'Installing completion for bash' in result.stdout
#                 mock_write.assert_called_once()

#     def test_install_completion_bash(self, runner: CliRunner) -> None:
#         """Test completion installation for bash."""
#         with patch('pathlib.Path.write_text') as mock_write:
#             result = runner.invoke(app, ['--install-completion', '--shell', 'bash'])
#             assert result.exit_code == 0
#             assert 'Installing completion for bash' in result.stdout
#             mock_write.assert_called_once()

#     def test_install_completion_zsh(self, runner: CliRunner) -> None:
#         """Test completion installation for zsh."""
#         with patch('pathlib.Path.mkdir') as mock_mkdir:
#             with patch('pathlib.Path.write_text') as mock_write:
#                 result = runner.invoke(app, ['--install-completion', '--shell', 'zsh'])
#                 assert result.exit_code == 0
#                 assert 'Installing completion for zsh' in result.stdout
#                 mock_mkdir.assert_called_once()
#                 mock_write.assert_called_once()

#     def test_install_completion_fish(self, runner: CliRunner) -> None:
#         """Test completion installation for fish."""
#         with patch('pathlib.Path.mkdir') as mock_mkdir:
#             with patch('pathlib.Path.write_text') as mock_write:
#                 result = runner.invoke(app, ['--install-completion', '--shell', 'fish'])
#                 assert result.exit_code == 0
#                 assert 'Installing completion for fish' in result.stdout
#                 mock_mkdir.assert_called_once()
#                 mock_write.assert_called_once()

#     def test_install_completion_unsupported_shell(self, runner: CliRunner) -> None:
#         """Test completion installation for unsupported shell."""
#         result = runner.invoke(app, ['--install-completion', '--shell', 'unsupported'])
#         assert result.exit_code == 0
#         assert 'Unsupported shell: unsupported' in result.stdout

#     def test_install_completion_error_handling(self, runner: CliRunner) -> None:
#         """Test completion installation error handling."""
#         with patch('typer.completion.get_completion_script', side_effect=Exception('Test error')):
#             result = runner.invoke(app, ['--install-completion', '--shell', 'bash'])
#             assert result.exit_code == 0
#             assert 'Error installing completion: Test error' in result.stdout

#     def test_install_completion_function_directly(self, tmp_path: Path) -> None:
#         """Test install_completion function directly."""
#         with patch.dict(os.environ, {'SHELL': '/bin/bash'}):
#             with patch('pathlib.Path.home', return_value=tmp_path):
#                 with patch('typer.completion.get_completion_script', return_value='completion code'):
#                     install_completion('')

#                     completion_file = tmp_path / '.bash_completion'
#                     assert completion_file.exists()
#                     assert completion_file.read_text() == 'completion code'


class TestSubApps:
    """Test that sub-apps are properly registered."""

    def test_config_subapp_registered(self, runner: CliRunner) -> None:
        """Test that config subapp is registered."""
        result = runner.invoke(app, ['config', '--help'])
        assert result.exit_code == 0
        assert 'config commands' in result.stdout

    def test_kernel_subapp_registered(self, runner: CliRunner) -> None:
        """Test that kernel subapp is registered."""
        result = runner.invoke(app, ['kernel', '--help'])
        assert result.exit_code == 0
        assert 'kernel commands' in result.stdout

    def test_compile_subapp_registered(self, runner: CliRunner) -> None:
        """Test that compile subapp is registered."""
        result = runner.invoke(app, ['compile', '--help'])
        assert result.exit_code == 0
        assert 'compile commands' in result.stdout

    def test_project_subapp_registered(self, runner: CliRunner) -> None:
        """Test that project subapp is registered."""
        result = runner.invoke(app, ['project', '--help'])
        assert result.exit_code == 0
        assert 'project commands' in result.stdout
