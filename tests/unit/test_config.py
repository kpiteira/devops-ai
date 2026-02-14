"""Tests for config loader — .devops-ai/infra.toml parsing."""

from pathlib import Path

import pytest

from devops_ai.config import find_project_root, load_config, parse_mount

# --- Simple config (khealth-style, 12 lines) ---

SIMPLE_CONFIG = """\
[project]
name = "khealth"
prefix = "khealth"

[sandbox]
compose_file = "docker-compose.yml"

[sandbox.health]
endpoint = "/api/v1/health"
port_var = "KHEALTH_API_PORT"

[sandbox.ports]
KHEALTH_API_PORT = 8080
"""

# --- Complex config (ktrdr-style, 22 lines) ---

COMPLEX_CONFIG = """\
[project]
name = "ktrdr"
prefix = "ktrdr"

[sandbox]
compose_file = "docker-compose.sandbox.yml"

[sandbox.health]
endpoint = "/api/v1/health"
port_var = "KTRDR_API_PORT"
timeout = 120

[sandbox.ports]
KTRDR_API_PORT = 8000
KTRDR_DB_PORT = 5432
KTRDR_WORKER_PORT_1 = 5003
KTRDR_WORKER_PORT_2 = 5004
KTRDR_WORKER_PORT_3 = 5005
KTRDR_WORKER_PORT_4 = 5006

[sandbox.mounts]
code = [
  "ktrdr/:/app/ktrdr",
  "research_agents/:/app/research_agents",
  "tests/:/app/tests",
  "config/:/app/config:ro",
]
code_targets = ["backend", "backtest-worker", "training-worker"]
shared = ["data/:/app/data", "models/:/app/models", "strategies/:/app/strategies"]
shared_targets = ["backend", "backtest-worker", "training-worker"]
"""

# --- No sandbox section ---

NO_SANDBOX_CONFIG = """\
[project]
name = "simple-project"
"""


def _write_config(tmp_path: Path, content: str) -> Path:
    """Write infra.toml under a .devops-ai/ directory and return the project root."""
    config_dir = tmp_path / ".devops-ai"
    config_dir.mkdir()
    (config_dir / "infra.toml").write_text(content)
    return tmp_path


class TestParseSimpleConfig:
    def test_project_name(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.project_name == "khealth"

    def test_prefix(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.prefix == "khealth"

    def test_compose_file(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.compose_file == "docker-compose.yml"

    def test_has_sandbox(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.has_sandbox is True

    def test_ports(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert len(config.ports) == 1
        assert config.ports[0].env_var == "KHEALTH_API_PORT"
        assert config.ports[0].base_port == 8080

    def test_health(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.health_endpoint == "/api/v1/health"
        assert config.health_port_var == "KHEALTH_API_PORT"
        assert config.health_timeout == 60  # default


class TestParseComplexConfig:
    def test_project_name(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, COMPLEX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.project_name == "ktrdr"

    def test_ports(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, COMPLEX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert len(config.ports) == 6
        port_map = {p.env_var: p.base_port for p in config.ports}
        assert port_map["KTRDR_API_PORT"] == 8000
        assert port_map["KTRDR_DB_PORT"] == 5432

    def test_health_timeout(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, COMPLEX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.health_timeout == 120

    def test_code_mounts(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, COMPLEX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert len(config.code_mounts) == 4
        expected_targets = ["backend", "backtest-worker", "training-worker"]
        assert config.code_mount_targets == expected_targets

    def test_shared_mounts(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, COMPLEX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert len(config.shared_mounts) == 3
        expected_targets = ["backend", "backtest-worker", "training-worker"]
        assert config.shared_mount_targets == expected_targets


class TestParseNoSandboxSection:
    def test_has_sandbox_false(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, NO_SANDBOX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.has_sandbox is False

    def test_project_name_still_set(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, NO_SANDBOX_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.project_name == "simple-project"


class TestParseMountSyntax:
    def test_host_container(self) -> None:
        mount = parse_mount("src/:/app/src")
        assert mount.host == "src/"
        assert mount.container == "/app/src"
        assert mount.readonly is False

    def test_readonly(self) -> None:
        mount = parse_mount("config/:/app/config:ro")
        assert mount.host == "config/"
        assert mount.container == "/app/config"
        assert mount.readonly is True

    def test_invalid_flag_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Invalid mount syntax"):
            parse_mount("src/:/app/src:rw")


class TestMissingRequiredField:
    def test_no_project_name(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, "[project]\n")
        with pytest.raises(ValueError, match="name"):
            load_config(root)


class TestDefaults:
    def test_prefix_defaults_to_name(self, tmp_path: Path) -> None:
        config_text = '[project]\nname = "myapp"\n'
        root = _write_config(tmp_path, config_text)
        config = load_config(root)
        assert config is not None
        assert config.prefix == "myapp"

    def test_timeout_defaults_to_60(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.health_timeout == 60


class TestFindProjectRoot:
    def test_finds_root(self, tmp_path: Path) -> None:
        (tmp_path / ".devops-ai").mkdir()
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        result = find_project_root(subdir)
        assert result == tmp_path

    def test_not_found(self, tmp_path: Path) -> None:
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        result = find_project_root(subdir)
        assert result is None


class TestNoConfigFile:
    def test_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".devops-ai").mkdir()
        config = load_config(tmp_path)
        assert config is None


# --- Provisioning sections ---

PROVISIONING_CONFIG = """\
[project]
name = "myapp"
prefix = "myapp"

[sandbox]
compose_file = "docker-compose.yml"

[sandbox.ports]
MYAPP_PORT = 8080

[sandbox.env]
APP_ENV = "sandbox"
LOG_LEVEL = "DEBUG"

[sandbox.secrets]
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"
API_KEY = "op://dev-vault/myapp/api-key"
DB_PASSWORD = "localdev"

[sandbox.files]
"config.yaml" = "config.yaml"
".env" = ".env.example"
"""


class TestParseProvisioningEnv:
    def test_env_parsed(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, PROVISIONING_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.env == {"APP_ENV": "sandbox", "LOG_LEVEL": "DEBUG"}


class TestParseProvisioningSecrets:
    def test_secrets_parsed(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, PROVISIONING_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.secrets == {
            "TELEGRAM_BOT_TOKEN": "$TELEGRAM_BOT_TOKEN",
            "API_KEY": "op://dev-vault/myapp/api-key",
            "DB_PASSWORD": "localdev",
        }


class TestParseProvisioningFiles:
    def test_files_parsed(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, PROVISIONING_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.files == {
            "config.yaml": "config.yaml",
            ".env": ".env.example",
        }


class TestProvisioningSectionsMissing:
    def test_defaults_to_empty_dicts(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, SIMPLE_CONFIG)
        config = load_config(root)
        assert config is not None
        assert config.env == {}
        assert config.secrets == {}
        assert config.files == {}


class TestAllProvisioningSectionsTogether:
    def test_all_three_coexist(self, tmp_path: Path) -> None:
        root = _write_config(tmp_path, PROVISIONING_CONFIG)
        config = load_config(root)
        assert config is not None
        assert len(config.env) == 2
        assert len(config.secrets) == 3
        assert len(config.files) == 2
        # Existing fields still work
        assert config.project_name == "myapp"
        assert len(config.ports) == 1
