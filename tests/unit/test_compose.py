"""Tests for compose file parameterization."""

from pathlib import Path

from devops_ai.compose import (
    add_header_comment,
    comment_out_services,
    parameterize_ports,
    remove_depends_on,
    rewrite_compose,
)

SAMPLE_COMPOSE = """\
services:
  myapp:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      - jaeger

  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
    environment:
      - COLLECTOR_OTLP_ENABLED=true
"""

COMPOSE_WITH_COMMENTS = """\
# My existing comment
services:
  myapp:
    build: .
    ports:
      - "8080:8080"  # API port
"""


class TestParameterizeSimplePorts:
    def test_replaces_host_port(self) -> None:
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(
            SAMPLE_COMPOSE, port_map
        )
        assert '"${MYAPP_PORT:-8080}:8080"' in result

    def test_does_not_touch_obs_ports(self) -> None:
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(
            SAMPLE_COMPOSE, port_map
        )
        # Obs ports (16686, 4317) should stay unchanged
        assert '"16686:16686"' in result


class TestParameterizePreservesComments:
    def test_keeps_existing_comments(self) -> None:
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(
            COMPOSE_WITH_COMMENTS, port_map
        )
        assert "# My existing comment" in result


class TestCommentOutObservability:
    def test_jaeger_commented(self) -> None:
        obs = ["jaeger"]
        result = comment_out_services(SAMPLE_COMPOSE, obs)
        # The jaeger service block should be commented
        assert "# jaeger:" in result
        # App should not be commented
        assert "  myapp:" in result


class TestAddHeaderComment:
    def test_header_present(self) -> None:
        result = add_header_comment(SAMPLE_COMPOSE)
        assert "kinfra-managed" in result
        assert "sandbox isolation" in result


class TestParameterizeDifferentHostContainer:
    def test_different_host_container_ports(self) -> None:
        compose = """\
services:
  myapp:
    ports:
      - "8081:8080"
"""
        port_map = {"MYAPP_PORT": 8081}
        result = parameterize_ports(compose, port_map)
        assert '"${MYAPP_PORT:-8081}:8080"' in result


class TestSkipAlreadyParameterized:
    def test_leaves_existing_vars(self) -> None:
        already_param = """\
services:
  myapp:
    ports:
      - "${MYAPP_PORT:-8080}:8080"
"""
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(already_param, port_map)
        assert '"${MYAPP_PORT:-8080}:8080"' in result
        # Should not double-wrap
        assert "${${" not in result


class TestRemoveDependsOnObservability:
    def test_removes_jaeger_dep(self) -> None:
        obs = ["jaeger"]
        result = remove_depends_on(SAMPLE_COMPOSE, obs)
        # depends_on block should be removed entirely
        assert "depends_on" not in result
        # myapp should still exist
        assert "myapp:" in result
        # jaeger service definition still present (not removed)
        assert "jaeger:" in result


class TestBackupCreated:
    def test_backup_file(self, tmp_path: Path) -> None:
        compose_path = tmp_path / "docker-compose.yml"
        compose_path.write_text(SAMPLE_COMPOSE)
        port_map = {"MYAPP_PORT": 8080}
        obs = ["jaeger"]
        rewrite_compose(compose_path, port_map, obs)
        backup = tmp_path / "docker-compose.yml.bak"
        assert backup.exists()
        assert backup.read_text() == SAMPLE_COMPOSE


class TestRoundtripPreservesStructure:
    def test_build_preserved(self) -> None:
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(SAMPLE_COMPOSE, port_map)
        assert "build: ." in result

    def test_environment_preserved(self) -> None:
        port_map = {"MYAPP_PORT": 8080}
        result = parameterize_ports(SAMPLE_COMPOSE, port_map)
        assert "COLLECTOR_OTLP_ENABLED=true" in result
