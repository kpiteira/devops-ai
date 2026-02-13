"""Tests for kinfra init — project inspection + config generation."""

from pathlib import Path

from devops_ai.cli.init_cmd import (
    InitPlan,
    detect_project,
    detect_project_name,
    detect_services_from_compose,
    generate_infra_toml,
    identify_observability_services,
)
from devops_ai.config import load_config

SAMPLE_COMPOSE = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
  worker:
    image: python:3.12
    ports:
      - "5003:5003"
      - "5004:5004"
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
"""


class TestDetectServicesFromCompose:
    def test_extracts_services_and_ports(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        assert "myapp" in services
        assert services["myapp"]["ports"] == [
            {"host": 8080, "container": 8080}
        ]
        assert "worker" in services
        assert len(services["worker"]["ports"]) == 2
        assert "jaeger" in services

    def test_extracts_image(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        assert services["jaeger"]["image"] == (
            "jaegertracing/jaeger:latest"
        )
        assert services["myapp"]["image"] is None  # uses build


class TestIdentifyObservabilityServices:
    def test_detects_jaeger(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        obs = identify_observability_services(services)
        assert "jaeger" in obs

    def test_detects_prometheus(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        obs = identify_observability_services(services)
        assert "prometheus" in obs

    def test_detects_grafana(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        obs = identify_observability_services(services)
        assert "grafana" in obs

    def test_app_not_in_observability(self) -> None:
        services = detect_services_from_compose(SAMPLE_COMPOSE)
        obs = identify_observability_services(services)
        assert "myapp" not in obs
        assert "worker" not in obs


class TestDetectProjectName:
    def test_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-cool-app"\n'
        )
        name = detect_project_name(tmp_path)
        assert name == "my-cool-app"

    def test_from_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"name": "my-node-app"}\n'
        )
        name = detect_project_name(tmp_path)
        assert name == "my-node-app"

    def test_fallback_to_dir_name(self, tmp_path: Path) -> None:
        name = detect_project_name(tmp_path)
        assert name == tmp_path.name


class TestGenerateInfraToml:
    def test_simple_config(self) -> None:
        toml = generate_infra_toml(
            project_name="khealth",
            prefix="khealth",
            compose_file="docker-compose.yml",
            ports={"KHEALTH_API_PORT": 8080},
            health_endpoint="/api/v1/health",
            health_port_var="KHEALTH_API_PORT",
        )
        assert '[project]' in toml
        assert 'name = "khealth"' in toml
        assert '[sandbox.ports]' in toml
        assert 'KHEALTH_API_PORT = 8080' in toml
        assert '[sandbox.health]' in toml
        assert 'endpoint = "/api/v1/health"' in toml

    def test_parseable_by_config_loader(
        self, tmp_path: Path
    ) -> None:
        toml = generate_infra_toml(
            project_name="khealth",
            prefix="khealth",
            compose_file="docker-compose.yml",
            ports={"KHEALTH_API_PORT": 8080},
            health_endpoint="/api/v1/health",
            health_port_var="KHEALTH_API_PORT",
        )
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "infra.toml").write_text(toml)
        config = load_config(tmp_path)
        assert config is not None
        assert config.project_name == "khealth"
        assert config.ports[0].env_var == "KHEALTH_API_PORT"
        assert config.ports[0].base_port == 8080
        assert config.health_endpoint == "/api/v1/health"


class TestInitRewritesCompose:
    def test_init_parameterizes_compose(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        # Create a compose file
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
            'services:\n  myapp:\n    image: python:3.12\n'
            '    ports:\n      - "8080:8080"\n'
            '  jaeger:\n    image: jaegertracing/jaeger:latest\n'
            '    ports:\n      - "16686:16686"\n'
        )

        # Mock interactive prompts and Docker check
        with (
            patch(
                "devops_ai.cli.init_cmd.typer.prompt",
                side_effect=[
                    "testproj",  # project name
                    "testproj",  # prefix
                    "/health",   # health endpoint
                ],
            ),
            patch(
                "devops_ai.cli.init_cmd.typer.echo",
            ),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(project_root=tmp_path)

        assert code == 0
        # Config should be created
        assert (tmp_path / ".devops-ai" / "infra.toml").exists()
        # Compose should be parameterized
        content = compose.read_text()
        assert "${TESTPROJ_MYAPP_PORT:-8080}" in content
        # Jaeger should be commented out
        assert "# jaeger:" in content
        # Backup should exist
        assert (tmp_path / "docker-compose.yml.bak").exists()


class TestReinitDetectsExisting:
    def test_existing_config_detected(self, tmp_path: Path) -> None:
        from devops_ai.cli.init_cmd import check_existing_config

        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "infra.toml").write_text(
            '[project]\nname = "old"\n'
        )
        exists, name = check_existing_config(tmp_path)
        assert exists is True
        assert name == "old"

    def test_no_existing_config(self, tmp_path: Path) -> None:
        from devops_ai.cli.init_cmd import check_existing_config

        exists, name = check_existing_config(tmp_path)
        assert exists is False
        assert name is None


COMPOSE_APP_AND_JAEGER = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
"""

COMPOSE_APP_ONLY = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
"""

COMPOSE_EMPTY = """\
version: "3"
"""


class TestDetectProject:
    """Tests for detect_project() — the pure detection pipeline."""

    def test_detects_compose_with_app_and_obs(
        self, tmp_path: Path
    ) -> None:
        """detect_project returns correct InitPlan for app + Jaeger."""
        (tmp_path / "docker-compose.yml").write_text(
            COMPOSE_APP_AND_JAEGER
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\n'
        )

        plan = detect_project(tmp_path)

        assert isinstance(plan, InitPlan)
        assert plan.project_name == "test-proj"
        assert plan.prefix == "test-proj"
        assert plan.compose_file == "docker-compose.yml"
        assert plan.compose_path == tmp_path / "docker-compose.yml"
        assert "jaeger" in plan.obs_services
        assert "myapp" in plan.app_services
        assert "jaeger" not in plan.app_services
        assert len(plan.ports) > 0
        assert plan.health_endpoint == "/api/v1/health"
        assert "[project]" in plan.toml_content

    def test_detects_compose_no_obs(self, tmp_path: Path) -> None:
        """detect_project handles compose with no obs services."""
        (tmp_path / "docker-compose.yml").write_text(COMPOSE_APP_ONLY)

        plan = detect_project(tmp_path)

        assert plan.obs_services == []
        assert "myapp" in plan.app_services

    def test_handles_no_compose_file(self, tmp_path: Path) -> None:
        """detect_project handles missing compose file gracefully."""
        plan = detect_project(tmp_path)

        assert plan.compose_file == "docker-compose.yml"
        assert plan.services == {}
        assert plan.obs_services == []
        assert plan.app_services == {}
        assert plan.ports == {}

    def test_handles_empty_compose(self, tmp_path: Path) -> None:
        """detect_project handles compose with no services key."""
        (tmp_path / "docker-compose.yml").write_text(COMPOSE_EMPTY)

        plan = detect_project(tmp_path)

        assert plan.services == {}
        assert plan.obs_services == []
        assert plan.app_services == {}

    def test_existing_interactive_flow_unchanged(
        self, tmp_path: Path
    ) -> None:
        """init_command interactive flow still works after refactor."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        compose = tmp_path / "docker-compose.yml"
        compose.write_text(COMPOSE_APP_AND_JAEGER)

        with (
            patch(
                "devops_ai.cli.init_cmd.typer.prompt",
                side_effect=[
                    "testproj",  # project name
                    "testproj",  # prefix
                    "/health",   # health endpoint
                ],
            ),
            patch("devops_ai.cli.init_cmd.typer.echo"),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(project_root=tmp_path)

        assert code == 0
        assert (tmp_path / ".devops-ai" / "infra.toml").exists()
