import os
from pathlib import Path
from typing import Any, Literal, Self

import appdirs
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource, PydanticBaseSettingsSource

from .constants import ERROR_SYMBOL, GOOD_SYMBOL, INFO_SYMBOL, SUCCESS_SYMBOL, WARNING_SYMBOL, console

GLOBAL_CONFIG_FILE = Path(appdirs.user_config_dir('etch')) / 'config.yaml'
LOCAL_CONFIG_FILE = Path('etch.yaml')


class WorkspaceConfig(BaseModel):
    build_dir: Path = Field(default=Path('./build'), description='Build directory')
    kernel_dirs: list[Path] = Field(
        default=[Path('kernel'), Path('kernels'), Path('ml_import')],
        description='List of directories to search for kernels',
    )


# class ApiSettings(BaseModel):
#     """API configuration settings."""

#     email: str = Field(default='', description='Email for API authentication')
#     password: str = Field(default='', description='Password for API authentication')
#     base_url: str = Field(default='http://localhost:8000', description='Base URL for the API')
#     api_key: str | None = Field(default=None, description='API key for authentication')
#     refresh_token: str | None = Field(default=None, description='Refresh token for API sessions')


class ToolPath(BaseModel):
    name: str
    path: Path
    validated: bool = Field(default=False, description='Whether the path has been validated')


class ConfigFile(YamlConfigSettingsSource):
    """Custom configuration file source that loads settings from a YAML file."""

    def __init__(self, settings_cls: type[BaseSettings], yaml_file: Path) -> None:
        super().__init__(settings_cls, yaml_file=yaml_file)
        self.settings_cls = settings_cls
        self.yaml_file = yaml_file

    def set(self, key: str, value: Any) -> None:
        """Set a specific setting in the YAML file."""
        data = self.settings_cls().model_dump()
        data[key] = value
        with self.yaml_file.open('w') as f:
            yaml.dump(data, f)


class AppSettings(BaseSettings):
    """
    Etch application settings.

    Loads configuration in this order (later sources override earlier ones):
    1. Default values
    2. ~/.config/etch/config.yaml (user/system config)
    3. etch.yaml (project local config)
    4. Environment variables with ETCH_ prefix
    """

    # Application settings
    debug: bool = Field(default=False, description='Enable debug mode')
    log_level: str = Field(default='INFO', description='Logging level')

    # API configuration
    api_host: str = Field(default='localhost', description='API server host')
    api_key: str | None = Field(default=None, description='API authentication key')
    refresh_token: str | None = Field(default=None, description='API refresh token')

    install_dir: Path = Path(appdirs.user_data_dir('bside')) / 'install'

    # install_dir: Path = Field(
    #     default=Path(appdirs.user_data_dir('etch')),
    #     description='Installation directory for Etch',
    # )

    # Paths
    # tools: list[ToolPath] = Field(
    #     default_factory=lambda: [
    #         ToolPath(name='cmake', path=Path('cmake'), validated=False),
    #         ToolPath(name='ninja', path=Path('ninja'), validated=False),
    #         ToolPath(name='clang', path=Path('clang'), validated=False),
    #     ],
    #     description='List of tool paths with validation status',
    # )

    # workspace: WorkspaceConfig = Field(default=WorkspaceConfig(), description='Workspace paths')

    model_config = SettingsConfigDict(
        # Environment variables override everything
        nested_model_default_partial_update=True,
        env_prefix='ETCH_',
        env_file=Path('etch.env'),
        env_file_encoding='utf-8',
        case_sensitive=False,
        # Create missing directories if needed
        extra='ignore',  # Ignore unknown fields
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Later sources override earlier ones (env_settings has highest priority)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            ConfigFile(settings_cls, yaml_file=GLOBAL_CONFIG_FILE),
            ConfigFile(settings_cls, yaml_file=LOCAL_CONFIG_FILE),
        )


# ============================================================================

# ============================================================================


class SettingsManager:
    _instance: AppSettings | None = None

    @classmethod
    def get_settings(cls) -> AppSettings:
        if cls._instance is None:
            console.print('Loading settings')
            cls._instance = AppSettings()
        return cls._instance

    @classmethod
    def set_settings(cls, settings: AppSettings) -> None:
        """Inject custom settings (useful for testing)."""
        cls._instance = settings

    @classmethod
    def reload(cls) -> AppSettings:
        """Force reload settings."""
        cls._instance = None
        # Force re-parsing by creating a fresh instance
        cls._instance = AppSettings()
        return cls._instance


# Convenience function
def get_settings() -> AppSettings:
    return SettingsManager.get_settings()


# Convenience function
def refresh_settings() -> AppSettings:
    return SettingsManager.reload()


def set_value(key: str, value: Any, is_global: bool = False) -> bool:
    """Set a value in the settings."""
    settings = get_settings()
    if hasattr(settings, key):
        setattr(settings, key, value)
        return save_settings(is_global=is_global)
    else:
        console.print(f'[red]Setting {key} does not exist in the configuration.[/red]')
        return False


def save_settings(is_global: bool = False) -> bool:
    """Save the current settings to the appropriate config file."""
    config_file = GLOBAL_CONFIG_FILE if is_global else LOCAL_CONFIG_FILE

    settings = get_settings()
    data = settings.model_dump()
    for key, value in data.items():
        if isinstance(value, Path):
            data[key] = str(value)

    with config_file.open('w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return True


#     if is_global:
#         config_file = GLOBAL_CONFIG_FILE
#     else:
#         config_file = LOCAL_CONFIG_FILE

#     settings = get_settings()
#     # settings.save(config_file)
#     console.print(f'{SUCCESS_SYMBOL} Settings saved to {config_file}')
#     return True
