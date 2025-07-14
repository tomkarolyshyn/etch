import os
from pathlib import Path
from typing import Any, Literal, Self

import appdirs
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import ERROR_SYMBOL, GOOD_SYMBOL, INFO_SYMBOL, SUCCESS_SYMBOL, WARNING_SYMBOL, console

GLOBAL_CONFIG_FILE = Path(appdirs.user_config_dir('etch')) / 'config.yaml'
LOCAL_CONFIG_FILE = Path('etch.yaml')

# Default configuration template
DEFAULT_CONFIG = """# Etch Configuration
# Generated automatically - edit as needed

# Application settings
debug: false
log_level: INFO

# API configuration
api_host: localhost
api_port: 8000

# Feature flags
enable_caching: true
enable_monitoring: false

# Tool paths
tools:
  - name: cmake
    path: cmake
    validated: false
  - name: ninja
    path: ninja
    validated: false
  - name: clang
    path: clang
    validated: false

# Workspace configuration
workspace:
  build_dir: ./build
  kernel_dirs:
    - kernels
"""


class WorkspaceConfig(BaseModel):
    build_dir: Path = Field(default=Path('./build'), description='Build directory')
    kernel_dirs: list[Path] = Field(
        default=[Path('kernel'), Path('kernels'), Path('ml_import')],
        description='List of directories to search for kernels',
    )


class ToolPath(BaseModel):
    name: str
    path: Path
    validated: bool = Field(default=False, description='Whether the path has been validated')


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
    api_port: int = Field(default=8000, description='API server port')
    api_key: str | None = Field(default=None, description='API authentication key')

    # Feature flags
    enable_caching: bool = Field(default=True, description='Enable response caching')
    enable_monitoring: bool = Field(default=False, description='Enable monitoring')

    install_dir: Path = Field(
        default=Path(appdirs.user_data_dir('etch')),
        description='Installation directory for Etch',
    )

    # Paths
    tools: list[ToolPath] = Field(
        default_factory=lambda: [
            ToolPath(name='cmake', path=Path('cmake'), validated=False),
            ToolPath(name='ninja', path=Path('ninja'), validated=False),
            ToolPath(name='clang', path=Path('clang'), validated=False),
        ],
        description='List of tool paths with validation status',
    )

    workspace: WorkspaceConfig = Field(default=WorkspaceConfig(), description='Workspace paths')

    model_config = SettingsConfigDict(
        # YAML files in order of precedence (last wins)
        yaml_file=[
            GLOBAL_CONFIG_FILE,  # System/user config
            LOCAL_CONFIG_FILE,  # Local project config
        ],
        # Environment variables override everything
        env_prefix='ETCH_',
        env_file_encoding='utf-8',
        case_sensitive=False,
        # Create missing directories if needed
        extra='ignore',  # Ignore unknown fields
    )

    @classmethod
    def load(cls) -> 'AppSettings':
        """
        Load settings with proper layering: defaults -> global -> local -> env vars.

        Returns:
            AppSettings: Configured settings instance
        """
        # Start with defaults
        settings = cls()

        # Load global config if it exists
        if GLOBAL_CONFIG_FILE.exists():
            try:
                with open(GLOBAL_CONFIG_FILE, encoding='utf-8') as f:
                    global_config = yaml.safe_load(f)
                    if global_config:
                        # Merge global config into settings
                        settings = cls.from_dict({**settings.model_dump(), **global_config})
                        console.print(f'{GOOD_SYMBOL} Loaded global config from {GLOBAL_CONFIG_FILE}')
            except Exception as e:
                console.print(f'{ERROR_SYMBOL} Error loading global config: {e}')
        else:
            console.print(f'{INFO_SYMBOL} Global config not found at {GLOBAL_CONFIG_FILE}')
            # Create default global config
            GLOBAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            GLOBAL_CONFIG_FILE.write_text(DEFAULT_CONFIG)
            console.print(f'{GOOD_SYMBOL} Created default global config at {GLOBAL_CONFIG_FILE}')

        # Load local config if it exists (overlays global)
        if LOCAL_CONFIG_FILE.exists():
            try:
                with open(LOCAL_CONFIG_FILE, encoding='utf-8') as f:
                    local_config = yaml.safe_load(f)
                    if local_config:
                        # Merge local config over existing settings
                        settings = cls.from_dict({**settings.model_dump(), **local_config})
                        console.print(f'{GOOD_SYMBOL} Loaded local config from {LOCAL_CONFIG_FILE}')
            except Exception as e:
                console.print(f'{ERROR_SYMBOL} Error loading local config: {e}')
        else:
            console.print(f'{INFO_SYMBOL} Local config not found at {LOCAL_CONFIG_FILE}')
            # Create default local config
            LOCAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            settings.save('local')
            console.print(f'{GOOD_SYMBOL}    Created default local config at {LOCAL_CONFIG_FILE}')

        # Environment variables are automatically loaded by pydantic-settings
        return settings

    def _print_config_sources(self) -> None:
        """Print which config sources were loaded."""
        console.print('Configuration loaded from:')

        # Show loading order and which files were found
        console.print('  1. Defaults (built-in values)')

        if GLOBAL_CONFIG_FILE.exists():
            console.print(f'  2. {GOOD_SYMBOL} Global config: {GLOBAL_CONFIG_FILE}')
        else:
            console.print(f'  2. {INFO_SYMBOL} Global config: {GLOBAL_CONFIG_FILE} (not found)')

        if LOCAL_CONFIG_FILE.exists():
            console.print(f'  3. {GOOD_SYMBOL} Local config: {LOCAL_CONFIG_FILE} (overlays global)')
        else:
            console.print(f'  3. {INFO_SYMBOL} Local config: {LOCAL_CONFIG_FILE} (not found)')

        env_vars = [key for key in os.environ if key.startswith('ETCH_')]
        if env_vars:
            console.print(f'  4. {GOOD_SYMBOL} Environment variables: {", ".join(env_vars)} (highest priority)')
        else:
            console.print(f'  4. {INFO_SYMBOL} No ETCH_* environment variables found')

        console.print('\nNote: Later sources override earlier ones (local overlays global)')

    def save(self, config_type: Literal['global', 'local'] = 'local') -> None:
        """
        Save current settings to a YAML file.

        Args:
            config_type: Either "user" (saves to ~/.config/etch/config.yaml)
                        or "local" (saves to etch.yaml)
            file_path: Optional custom file path (overrides config_type)

        Returns:
            Path: The path where settings were saved
        """

        # Get the data as a dictionary
        data = self.model_dump()
        cleaned_data = self._clean_nested_data(data)

        # Ensure parent directory exists
        cfgfile = GLOBAL_CONFIG_FILE if config_type == 'global' else LOCAL_CONFIG_FILE

        cfgfile.parent.mkdir(parents=True, exist_ok=True)

        # Default YAML dump options for clean output
        yaml_options = {
            'default_flow_style': False,  # Use block style, not inline
            'indent': 2,  # 2-space indentation
            'width': 80,  # Line width
            'allow_unicode': True,  # Support unicode characters
            'sort_keys': False,  # Preserve field order
        }

        with open(cfgfile, 'w', encoding='utf-8') as f:
            f.write('# Etch Configuration\n')
            f.write('# Generated automatically - edit as needed\n')
            f.write(f'# File: {cfgfile}\n\n')
            yaml.dump(cleaned_data, f, **yaml_options)  # type: ignore[call-overload]

        console.print(f'✅ Configuration saved to {cfgfile}')

    def _clean_nested_data(self, data: Any) -> Any:
        """Recursively clean data for YAML serialization"""
        if isinstance(data, dict):
            return {key: self._clean_nested_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._clean_nested_data(item) for item in data]
        elif isinstance(data, Path):
            return str(data)
        else:
            return data

    def update_setting(self, key: str, value: Any, save: bool = True) -> None:
        """
        Update a single setting and optionally save to local config.

        Args:
            key: Setting key (e.g., 'debug', 'api.port')
            value: New value
            save: Whether to save to etch.yaml immediately

        Example:
            settings.update_setting('debug', True)
            settings.update_setting('api.port', 9000)
        """
        # Handle nested keys (e.g., 'api.port' -> api_port)
        if '.' in key:
            section, field = key.split('.', 1)
            key = f'{section}_{field}'

        # Validate that the field exists
        if not hasattr(self, key):
            raise ValueError(f'Unknown setting: {key}')

        # Use Pydantic's model_copy to update and re-validate
        updated = self.model_copy(update={key: value})
        self.__dict__.update(updated.__dict__)
        console.print(f'Updated {key} = {getattr(self, key)}')

        if save:
            self.save('local')

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> 'AppSettings':
        """
        Create settings instance from a dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            AppSettings: New settings instance
        """
        return cls(**config_dict)

    def reset_to_defaults(self, save: bool = False) -> None:
        """
        Reset all settings to their default values.

        Args:
            save: Whether to save the defaults to local config
        """
        defaults = AppSettings()
        for field_name, _ in self.__class__.model_fields.items():
            default_value = getattr(defaults, field_name)
            setattr(self, field_name, default_value)

        console.print('Settings reset to defaults')

        if save:
            self.save('local')


# ============================================================================

# ============================================================================


class SettingsManager:
    _instance: AppSettings | None = None

    @classmethod
    def get_settings(cls) -> AppSettings:
        if cls._instance is None:
            console.print('Loading settings')
            cls._instance = AppSettings.load()
        return cls._instance

    @classmethod
    def set_settings(cls, settings: AppSettings) -> None:
        """Inject custom settings (useful for testing)."""
        cls._instance = settings

    @classmethod
    def reload(cls) -> AppSettings:
        """Force reload settings."""
        cls._instance = None
        return cls.get_settings()


# Convenience function
def get_settings() -> AppSettings:
    return SettingsManager.get_settings()
