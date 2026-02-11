"""Tests for the observability compose template."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "observability"
    / "docker-compose.yml"
)


def _load_template() -> dict:
    yml = YAML()
    return yml.load(TEMPLATE_PATH.read_text())


def test_template_is_valid_yaml() -> None:
    data = _load_template()
    assert isinstance(data, dict)
    assert "services" in data


def test_template_services() -> None:
    data = _load_template()
    services = data["services"]
    expected = {"devops-ai-jaeger", "devops-ai-grafana", "devops-ai-prometheus"}
    assert set(services.keys()) == expected


def test_template_ports_in_4xxxx_range() -> None:
    data = _load_template()
    for svc_name, svc in data["services"].items():
        for port_mapping in svc.get("ports", []):
            # port_mapping can be "host:container" or "ip:host:container"
            parts = str(port_mapping).split(":")
            host_port = int(parts[-2])  # second-to-last is always the host port
            assert 40000 <= host_port <= 49999, (
                f"{svc_name}: host port {host_port} not in 4xxxx range"
            )


def test_template_container_names() -> None:
    data = _load_template()
    for svc_name, svc in data["services"].items():
        cname = svc.get("container_name", "")
        assert cname.startswith("devops-ai-"), (
            f"{svc_name}: container_name {cname!r} missing devops-ai- prefix"
        )


def test_template_network_external() -> None:
    data = _load_template()
    networks = data.get("networks", {})
    obs_net = networks.get("devops-ai-observability", {})
    assert obs_net.get("external") is True


def test_template_otlp_enabled() -> None:
    data = _load_template()
    jaeger = data["services"]["devops-ai-jaeger"]
    env = jaeger.get("environment", {})
    # environment can be a list of "KEY=VALUE" or a dict
    if isinstance(env, list):
        env_dict = dict(item.split("=", 1) for item in env)
    else:
        env_dict = env
    assert env_dict.get("COLLECTOR_OTLP_ENABLED") == "true"
