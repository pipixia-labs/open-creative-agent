"""System configuration for local Open Creative Agent runs."""

import json
import os
from typing import Optional

import json5
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, model_validator

from conf.path import CONF_ROOT


load_dotenv()


class SystemConfig(BaseModel):
    """Configuration values required by the local runtime."""

    executor_replan_enabled: bool = True
    llm_model: str
    orchestrator_llm_model: str
    critic_llm_model: str
    plan_critic_iter_num: int
    html_gen_llm_model: str
    html_gen_thinking_level: Optional[str] = None
    executor_llm_model: str
    thinking_level: str = "medium"
    art_knowledge_thinking_level: Optional[str] = None
    art_knowledge_llm_model: str
    article_llm_model: str
    science_llm_model: str
    api_port: int
    app_name: str
    user_id_default: str
    session_id_default_prefix: str
    max_iterations_orchestrator: int
    max_search_count: int
    image_output_dir: str
    video_output_dir: str
    log_level: str
    log_file: str
    retention: str
    rotation: str
    DEBUG_USERS: list[str]
    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    session_database_dir: str = os.path.join(base_dir, "database", "session_database")

    @model_validator(mode="after")
    def resolve_paths(self) -> "SystemConfig":
        """Resolve project-relative output directories to absolute paths."""
        os.makedirs(self.session_database_dir, exist_ok=True)
        for field_name in ("image_output_dir", "video_output_dir"):
            path_value = getattr(self, field_name)
            if path_value and not os.path.isabs(path_value):
                setattr(self, field_name, os.path.join(self.base_dir, path_value))
        return self

    @model_validator(mode="after")
    def apply_runtime_env_overrides(self) -> "SystemConfig":
        """Apply local runtime overrides from environment variables."""
        str_map = {
            "OCA_THINKING_LEVEL": "thinking_level",
            "OCA_HTML_GEN_THINKING_LEVEL": "html_gen_thinking_level",
            "OCA_ART_KNOWLEDGE_THINKING_LEVEL": "art_knowledge_thinking_level",
            "OCA_LOCAL_USER_ID": "user_id_default",
        }
        int_map = {
            "OCA_PORT": "api_port",
        }

        for env_name, field_name in str_map.items():
            val = os.getenv(env_name)
            if val is not None:
                setattr(self, field_name, val)

        for env_name, field_name in int_map.items():
            val = os.getenv(env_name)
            if val is None or not val.strip():
                continue
            try:
                setattr(self, field_name, int(val))
            except ValueError:
                continue

        return self


def load_system_config(config_file_path: str) -> SystemConfig:
    """Load and validate system configuration from a JSON5 file."""
    try:
        with open(config_file_path, "r") as file:
            config_data = json5.load(file)
            config_data = resolve_env_placeholders(config_data)
            return SystemConfig(**config_data)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
        print(
            f"FATAL: Could not load system configuration from {config_file_path}. Reason: {exc}"
        )
        raise


def resolve_env_placeholders(value):
    """Recursively resolve `${ENV_NAME}` placeholders in config values."""
    if isinstance(value, dict):
        return {key: resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_env_placeholders(item) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1].strip()
        env_value = os.getenv(env_name)
        if env_value is None:
            return value
        if env_value.isdigit():
            return int(env_value)
        return env_value
    return value


config_name = "system.json"
SYS_CONFIG: SystemConfig = load_system_config(os.path.join(CONF_ROOT, "jsons", config_name))
