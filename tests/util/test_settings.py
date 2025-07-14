import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from etch.util.settings import (
    GLOBAL_CONFIG_FILE,
    LOCAL_CONFIG_FILE,
    AppSettings,
    SettingsManager,
    get_settings,
)


@pytest.fixture
def temp_local_config(tmp_path: Path) -> Path:
    """Create a temporary local config file for testing."""
    settings_path = tmp_path / 'etch.yaml'
    settings_content = """# Test local settings
debug: true
log_level: DEBUG
api_host: testhost
api_port: 9000
enable_caching: false
tools:
  - name: cmake
    path: /usr/bin/cmake
    validated: true
  - name: ninja
    path: /usr/bin/ninja
    validated: false
workspace:
  build_dir: ./test_build
  kernel_dirs:
    - kernel
    - test_kernels
"""
    settings_path.write_text(settings_content)
    return settings_path


@pytest.fixture
def temp_global_config(tmp_path: Path) -> Path:
    """Create a temporary global config file for testing."""
    settings_path = tmp_path / 'config.yaml'
    settings_content = """# Test global settings
debug: false
log_level: WARNING
api_host: globalhost
api_port: 8080
enable_caching: true
tools:
  - name: cmake
    path: /usr/bin/cmake
    validated: false
  - name: ninja
    path: /usr/bin/ninja
    validated: true
"""
    settings_path.write_text(settings_content)
    return settings_path


@pytest.fixture
def clean_settings() -> Generator[None, None, None]:
    """Clean up SettingsManager singleton between tests."""
    SettingsManager._instance = None
    yield
    SettingsManager._instance = None


def test_load_default_settings() -> None:
    """Test loading default settings."""
    settings = AppSettings()
    assert settings.debug is False
    assert settings.log_level == 'INFO'
    assert settings.api_host == 'localhost'
    assert settings.api_port == 8000
    assert settings.enable_caching is True
    assert len(settings.tools) == 3
    assert settings.tools[0].name == 'cmake'


def test_load_from_local_config_only(temp_local_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading settings from local config file only."""
    # Change to temp directory so etch.yaml is found
    monkeypatch.chdir(temp_local_config.parent)

    # Create a mock Path object for global config that doesn't exist
    mock_global_config = temp_local_config.parent / 'nonexistent_global.yaml'

    # Mock global config file to not exist
    with patch('etch.util.settings.GLOBAL_CONFIG_FILE', mock_global_config):
        settings = AppSettings.load()
        assert settings.debug is True
        assert settings.log_level == 'DEBUG'
        assert settings.api_host == 'testhost'
        assert settings.api_port == 9000
        assert settings.enable_caching is False
        assert len(settings.tools) == 2
        assert settings.tools[0].name == 'cmake'
        assert settings.tools[0].validated is True


def test_load_from_global_config_only(
    temp_global_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test loading settings from global config file only."""
    # Change to temp directory with no local config
    monkeypatch.chdir(tmp_path)

    # Create a mock Path object for local config that doesn't exist
    mock_local_config = tmp_path / 'nonexistent_local.yaml'

    # Mock global config file to use our temp file
    with (
        patch('etch.util.settings.GLOBAL_CONFIG_FILE', temp_global_config),
        patch('etch.util.settings.LOCAL_CONFIG_FILE', mock_local_config),
        patch.object(AppSettings, 'save'),
    ):
        settings = AppSettings.load()
        assert settings.debug is False
        assert settings.log_level == 'WARNING'
        assert settings.api_host == 'globalhost'
        assert settings.api_port == 8080
        assert settings.enable_caching is True
        assert len(settings.tools) == 2
        assert settings.tools[0].name == 'cmake'
        assert settings.tools[0].validated is False


def test_load_with_both_configs(
    temp_global_config: Path, temp_local_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test loading settings with both global and local configs (local should override global)."""
    # Change to temp directory so etch.yaml is found
    monkeypatch.chdir(temp_local_config.parent)

    # Mock global config file to use our temp file
    with patch('etch.util.settings.GLOBAL_CONFIG_FILE', temp_global_config):
        settings = AppSettings.load()
        # Local config should override global
        assert settings.debug is True  # from local (overrides global false)
        assert settings.log_level == 'DEBUG'  # from local (overrides global WARNING)
        assert settings.api_host == 'testhost'  # from local (overrides global globalhost)
        assert settings.api_port == 9000  # from local (overrides global 8080)
        assert settings.enable_caching is False  # from local (overrides global true)
        assert len(settings.tools) == 2
        assert settings.tools[0].name == 'cmake'
        assert settings.tools[0].validated is True  # from local


def test_load_creates_missing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load() creates missing config files."""
    # Change to temp directory with no config files
    monkeypatch.chdir(tmp_path)

    global_config_path = tmp_path / 'global' / 'config.yaml'
    local_config_path = tmp_path / 'etch.yaml'

    with (
        patch('etch.util.settings.GLOBAL_CONFIG_FILE', global_config_path),
        patch('etch.util.settings.LOCAL_CONFIG_FILE', local_config_path),
    ):
        settings = AppSettings.load()

        # Check that files were created
        assert global_config_path.exists()
        assert local_config_path.exists()

        # Check that settings have defaults
        assert settings.debug is False
        assert settings.log_level == 'INFO'
        assert settings.api_host == 'localhost'
        assert settings.api_port == 8000


def test_settings_manager_singleton(clean_settings: None, tmp_path: Path) -> None:
    """Test that SettingsManager maintains singleton behavior."""
    # Create mock Path objects that don't exist
    mock_global_config = tmp_path / 'nonexistent_global.yaml'
    mock_local_config = tmp_path / 'nonexistent_local.yaml'

    with (
        patch('etch.util.settings.GLOBAL_CONFIG_FILE', mock_global_config),
        patch('etch.util.settings.LOCAL_CONFIG_FILE', mock_local_config),
        patch.object(AppSettings, 'save'),
    ):
        # First call should create instance
        settings1 = SettingsManager.get_settings()
        # Second call should return same instance
        settings2 = SettingsManager.get_settings()
        assert settings1 is settings2


def test_settings_manager_reload(clean_settings: None, tmp_path: Path) -> None:
    """Test that SettingsManager.reload() forces new instance."""
    # Create mock Path objects that don't exist
    mock_global_config = tmp_path / 'nonexistent_global.yaml'
    mock_local_config = tmp_path / 'nonexistent_local.yaml'

    with (
        patch('etch.util.settings.GLOBAL_CONFIG_FILE', mock_global_config),
        patch('etch.util.settings.LOCAL_CONFIG_FILE', mock_local_config),
        patch.object(AppSettings, 'save'),
    ):
        settings1 = SettingsManager.get_settings()
        settings2 = SettingsManager.reload()
        # Should be different instances after reload
        assert settings1 is not settings2


def test_settings_manager_set_settings(clean_settings: None) -> None:
    """Test injecting custom settings for testing."""
    custom_settings = AppSettings(debug=True, log_level='DEBUG')
    SettingsManager.set_settings(custom_settings)

    retrieved_settings = SettingsManager.get_settings()
    assert retrieved_settings is custom_settings
    assert retrieved_settings.debug is True
    assert retrieved_settings.log_level == 'DEBUG'


def test_convenience_get_settings(clean_settings: None, tmp_path: Path) -> None:
    """Test convenience function returns same as manager."""
    # Create mock Path objects that don't exist
    mock_global_config = tmp_path / 'nonexistent_global.yaml'
    mock_local_config = tmp_path / 'nonexistent_local.yaml'

    with (
        patch('etch.util.settings.GLOBAL_CONFIG_FILE', mock_global_config),
        patch('etch.util.settings.LOCAL_CONFIG_FILE', mock_local_config),
        patch.object(AppSettings, 'save'),
    ):
        manager_settings = SettingsManager.get_settings()
        convenience_settings = get_settings()
        assert manager_settings is convenience_settings


def test_update_setting_valid_field() -> None:
    """Test setting a valid field."""
    settings = AppSettings()
    original_debug = settings.debug

    settings.update_setting('debug', not original_debug, save=False)
    assert settings.debug == (not original_debug)


def test_update_setting_nested_key() -> None:
    """Test setting field with nested key notation."""
    settings = AppSettings()

    settings.update_setting('api.host', 'newhost', save=False)
    assert settings.api_host == 'newhost'

    settings.update_setting('api.port', 9999, save=False)
    assert settings.api_port == 9999


def test_update_setting_invalid_field() -> None:
    """Test setting an invalid field raises ValueError."""
    settings = AppSettings()

    with pytest.raises(ValueError, match='Unknown setting: invalid_field'):
        settings.update_setting('invalid_field', 'value', save=False)


def test_update_setting_invalid_nested_field() -> None:
    """Test setting an invalid nested field raises ValueError."""
    settings = AppSettings()

    with pytest.raises(ValueError, match='Unknown setting: api_invalid'):
        settings.update_setting('api.invalid', 'value', save=False)


def test_from_dict() -> None:
    """Test creating settings from dictionary."""
    config_dict = {
        'debug': True,
        'log_level': 'DEBUG',
        'api_host': 'testhost',
        'api_port': 9000,
    }

    settings = AppSettings.from_dict(config_dict)
    assert settings.debug is True
    assert settings.log_level == 'DEBUG'
    assert settings.api_host == 'testhost'
    assert settings.api_port == 9000


def test_reset_to_defaults() -> None:
    """Test resetting settings to defaults."""
    settings = AppSettings(debug=True, log_level='DEBUG', api_host='custom')

    # Verify settings are not defaults
    assert settings.debug is True
    assert settings.log_level == 'DEBUG'
    assert settings.api_host == 'custom'

    # Reset to defaults
    settings.reset_to_defaults(save=False)

    # Verify settings are now defaults
    assert settings.debug is False
    assert settings.log_level == 'INFO'
    assert settings.api_host == 'localhost'


def test_save_global_config(tmp_path: Path) -> None:
    """Test saving global config."""
    settings = AppSettings(debug=True, log_level='DEBUG')

    global_config_path = tmp_path / 'config.yaml'

    with patch('etch.util.settings.GLOBAL_CONFIG_FILE', global_config_path):
        settings.save('global')

        assert global_config_path.exists()
        content = global_config_path.read_text()
        assert 'debug: true' in content
        assert 'log_level: DEBUG' in content


def test_save_local_config(tmp_path: Path) -> None:
    """Test saving local config."""
    settings = AppSettings(debug=True, log_level='DEBUG')

    local_config_path = tmp_path / 'etch.yaml'

    with patch('etch.util.settings.LOCAL_CONFIG_FILE', local_config_path):
        settings.save('local')

        assert local_config_path.exists()
        content = local_config_path.read_text()
        assert 'debug: true' in content
        assert 'log_level: DEBUG' in content
