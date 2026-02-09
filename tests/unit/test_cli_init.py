"""Tests for kinfra init — project inspection + config generation."""

from pathlib import Path

from devops_ai.cli.init_cmd import (
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
