"""Tests for kinfra init — project inspection + config generation."""

from pathlib import Path
from unittest.mock import patch

from devops_ai.cli.init_cmd import (
    InitPlan,
    detect_env_vars,
    detect_gitignored_mounts,
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


class TestInitDryRun:
    """Tests for --dry-run flag."""

    def test_dry_run_auto_prints_plan_writes_nothing(
        self, tmp_path: Path
    ) -> None:
        """--dry-run --auto: detection runs, output printed, no files."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        (tmp_path / "docker-compose.yml").write_text(
            COMPOSE_APP_AND_JAEGER
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\n'
        )

        echo_calls: list[str] = []
        with (
            patch(
                "devops_ai.cli.init_cmd.typer.echo",
                side_effect=lambda msg="": echo_calls.append(str(msg)),
            ),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(
                project_root=tmp_path, dry_run=True, auto=True
            )

        assert code == 0
        # No files should be created
        assert not (tmp_path / ".devops-ai" / "infra.toml").exists()
        assert not (tmp_path / "docker-compose.yml.bak").exists()
        # Output should contain project info
        output = "\n".join(echo_calls)
        assert "test-proj" in output
        assert "No files written" in output

    def test_dry_run_without_auto_still_prompts(
        self, tmp_path: Path
    ) -> None:
        """--dry-run alone (without --auto) still prompts, then previews."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        (tmp_path / "docker-compose.yml").write_text(
            COMPOSE_APP_AND_JAEGER
        )

        echo_calls: list[str] = []
        with (
            patch(
                "devops_ai.cli.init_cmd.typer.prompt",
                side_effect=[
                    "myproj",   # project name
                    "myproj",   # prefix
                    "/health",  # health endpoint
                ],
            ),
            patch(
                "devops_ai.cli.init_cmd.typer.echo",
                side_effect=lambda msg="": echo_calls.append(str(msg)),
            ),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(
                project_root=tmp_path, dry_run=True
            )

        assert code == 0
        # No files should be created
        assert not (tmp_path / ".devops-ai" / "infra.toml").exists()
        output = "\n".join(echo_calls)
        assert "No files written" in output


class TestInitAuto:
    """Tests for --auto flag."""

    def test_auto_creates_files_without_prompts(
        self, tmp_path: Path
    ) -> None:
        """--auto: uses detected defaults, creates files without prompts."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        compose = tmp_path / "docker-compose.yml"
        compose.write_text(COMPOSE_APP_AND_JAEGER)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\n'
        )

        with (
            patch("devops_ai.cli.init_cmd.typer.echo"),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(
                project_root=tmp_path, auto=True
            )

        assert code == 0
        # Config should be created
        assert (tmp_path / ".devops-ai" / "infra.toml").exists()
        toml = (tmp_path / ".devops-ai" / "infra.toml").read_text()
        assert 'name = "test-proj"' in toml
        # Compose should be parameterized
        content = compose.read_text()
        assert "${" in content
        # Jaeger should be commented out
        assert "# jaeger:" in content

    def test_auto_with_existing_config_updates(
        self, tmp_path: Path
    ) -> None:
        """--auto with existing config: auto-confirms update."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        compose = tmp_path / "docker-compose.yml"
        compose.write_text(COMPOSE_APP_ONLY)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "updated"\n'
        )
        # Pre-existing config
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "infra.toml").write_text(
            '[project]\nname = "old"\n'
        )

        with (
            patch("devops_ai.cli.init_cmd.typer.echo"),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(
                project_root=tmp_path, auto=True
            )

        assert code == 0
        toml = (tmp_path / ".devops-ai" / "infra.toml").read_text()
        assert 'name = "updated"' in toml

    def test_auto_with_health_endpoint_override(
        self, tmp_path: Path
    ) -> None:
        """--auto --health-endpoint /health: uses provided endpoint."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        (tmp_path / "docker-compose.yml").write_text(
            COMPOSE_APP_ONLY
        )

        with (
            patch("devops_ai.cli.init_cmd.typer.echo"),
            patch(
                "devops_ai.cli.init_cmd.check_docker_running",
                return_value=False,
            ),
        ):
            code = init_command(
                project_root=tmp_path,
                auto=True,
                health_endpoint="/health",
            )

        assert code == 0
        toml = (tmp_path / ".devops-ai" / "infra.toml").read_text()
        assert 'endpoint = "/health"' in toml

    def test_interactive_mode_unchanged(
        self, tmp_path: Path
    ) -> None:
        """No flags: interactive mode unchanged (prompts required)."""
        from unittest.mock import patch

        from devops_ai.cli.init_cmd import init_command

        compose = tmp_path / "docker-compose.yml"
        compose.write_text(COMPOSE_APP_ONLY)

        with (
            patch(
                "devops_ai.cli.init_cmd.typer.prompt",
                side_effect=[
                    "interproj",  # project name
                    "interproj",  # prefix
                    "/api/health",  # health endpoint
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
        toml = (tmp_path / ".devops-ai" / "infra.toml").read_text()
        assert 'name = "interproj"' in toml


# --- Env var detection ---

COMPOSE_WITH_ENV_VARS = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
    environment:
      - APP_SECRET=${APP_SECRET}
      - LOG_LEVEL=${LOG_LEVEL:-info}
      - CONFIG_PATH=/app/config.yaml
  worker:
    image: python:3.12
    environment:
      APP_SECRET: ${APP_SECRET}
      WORKER_TOKEN: ${WORKER_TOKEN}
"""

COMPOSE_WITH_VOLUMES = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
      - app-data:/app/persistent
      - ./.env:/app/.env

volumes:
  app-data:
"""


class TestDetectEnvVars:
    def test_finds_simple_var_references(self) -> None:
        candidates = detect_env_vars(COMPOSE_WITH_ENV_VARS, set())
        names = {c.name for c in candidates}
        assert "APP_SECRET" in names
        assert "WORKER_TOKEN" in names

    def test_finds_var_with_default(self) -> None:
        candidates = detect_env_vars(COMPOSE_WITH_ENV_VARS, set())
        log_level = next(c for c in candidates if c.name == "LOG_LEVEL")
        assert log_level.default == "info"

    def test_excludes_known_vars(self) -> None:
        known = {"APP_SECRET", "COMPOSE_PROJECT_NAME"}
        candidates = detect_env_vars(COMPOSE_WITH_ENV_VARS, known)
        names = {c.name for c in candidates}
        assert "APP_SECRET" not in names
        assert "LOG_LEVEL" in names

    def test_excludes_otel_and_compose_vars(self) -> None:
        known = {
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_RESOURCE_ATTRIBUTES",
            "COMPOSE_PROJECT_NAME",
        }
        compose = (
            "services:\n  app:\n    environment:\n"
            "      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}\n"
            "      - MY_VAR=${MY_VAR}\n"
        )
        candidates = detect_env_vars(compose, known)
        names = {c.name for c in candidates}
        assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in names
        assert "MY_VAR" in names

    def test_identifies_services(self) -> None:
        candidates = detect_env_vars(COMPOSE_WITH_ENV_VARS, set())
        app_secret = next(c for c in candidates if c.name == "APP_SECRET")
        assert "myapp" in app_secret.services
        assert "worker" in app_secret.services

    def test_handles_no_env_var_references(self) -> None:
        compose = "services:\n  app:\n    build: .\n"
        candidates = detect_env_vars(compose, set())
        assert candidates == []

    def test_deduplicates_vars(self) -> None:
        """Same var in multiple services → one candidate with both services."""
        candidates = detect_env_vars(COMPOSE_WITH_ENV_VARS, set())
        app_secret_entries = [c for c in candidates if c.name == "APP_SECRET"]
        assert len(app_secret_entries) == 1


class TestDetectGitignoredMounts:
    def test_identifies_gitignored_bind_mounts(
        self, tmp_path: Path
    ) -> None:
        # Mock git check-ignore: config.yaml is ignored, data/ is not
        def mock_check_ignore(
            cmd, capture_output, text, timeout, cwd,
        ):
            from unittest.mock import MagicMock

            path = cmd[-1]
            result = MagicMock()
            result.returncode = 0 if path == "config.yaml" else 1
            return result

        with patch("devops_ai.cli.init_cmd.subprocess.run", mock_check_ignore):
            candidates = detect_gitignored_mounts(
                COMPOSE_WITH_VOLUMES, tmp_path
            )

        host_paths = {c.host_path for c in candidates}
        assert "config.yaml" in host_paths

    def test_skips_named_volumes(self, tmp_path: Path) -> None:
        # All bind mounts non-ignored
        def mock_check_ignore(cmd, capture_output, text, timeout, cwd):
            from unittest.mock import MagicMock

            result = MagicMock()
            result.returncode = 1  # not ignored
            return result

        with patch("devops_ai.cli.init_cmd.subprocess.run", mock_check_ignore):
            candidates = detect_gitignored_mounts(
                COMPOSE_WITH_VOLUMES, tmp_path
            )

        # Named volume 'app-data' should never appear
        host_paths = {c.host_path for c in candidates}
        assert "app-data" not in host_paths
        assert "app-persistent" not in host_paths

    def test_checks_source_existence_and_example(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "config.yaml").write_text("setting: value")
        (tmp_path / ".env.example").write_text("KEY=val")

        def mock_check_ignore(cmd, capture_output, text, timeout, cwd):
            from unittest.mock import MagicMock

            path = cmd[-1]
            result = MagicMock()
            # config.yaml and .env are ignored
            result.returncode = 0 if path in ("config.yaml", ".env") else 1
            return result

        with patch("devops_ai.cli.init_cmd.subprocess.run", mock_check_ignore):
            candidates = detect_gitignored_mounts(
                COMPOSE_WITH_VOLUMES, tmp_path
            )

        config = next(c for c in candidates if c.host_path == "config.yaml")
        assert config.source_exists is True
        assert config.example_exists is False

        env_c = next(c for c in candidates if c.host_path == ".env")
        assert env_c.source_exists is False
        assert env_c.example_exists is True
        assert env_c.example_path == ".env.example"

    def test_handles_compose_with_no_bind_mounts(
        self, tmp_path: Path
    ) -> None:
        compose = "services:\n  app:\n    build: .\n"
        candidates = detect_gitignored_mounts(compose, tmp_path)
        assert candidates == []


class TestDetectProjectPopulatesNewFields:
    def test_env_var_candidates_populated(self, tmp_path: Path) -> None:
        compose = (
            "services:\n  myapp:\n    build: .\n"
            "    ports:\n      - \"8080:8080\"\n"
            "    environment:\n      - MY_SECRET=${MY_SECRET}\n"
        )
        (tmp_path / "docker-compose.yml").write_text(compose)

        plan = detect_project(tmp_path)

        assert hasattr(plan, "env_var_candidates")
        names = {c.name for c in plan.env_var_candidates}
        assert "MY_SECRET" in names
        # Port vars should be excluded
        for c in plan.env_var_candidates:
            assert c.name not in plan.ports
