from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_production_compose_uses_immutable_application_code():
    compose = (ROOT_DIR / "docker-compose.prod.yml").read_text()

    forbidden_source_mounts = (
        "./backend/static_src:/app/",
        "./backend/templates:/app/",
        "./backend/config:/app/",
        "./backend/apps:/app/",
        "./infra/scripts:/app/",
        "./infra/scripts/web-entrypoint.sh:/app/",
    )

    assert all(mount not in compose for mount in forbidden_source_mounts)
    assert "django_static:/usr/share/nginx/prenium-static:ro" in compose
    assert "condition: service_healthy" in compose
    assert compose.count("image: prenium-dtf-backend-prod:${APP_IMAGE_TAG:-local}") == 3
    assert compose.count("dockerfile: infra/docker/backend/Dockerfile") == 1


def test_docker_build_context_excludes_local_agent_artifacts():
    ignored = set((ROOT_DIR / ".dockerignore").read_text().splitlines())

    assert {".codex", ".impeccable", ".playwright-cli", "data", "graphify-out", "output"} <= ignored


def test_runtime_images_are_pinned_by_multi_arch_digest():
    backend_dockerfile = (ROOT_DIR / "infra" / "docker" / "backend" / "Dockerfile").read_text()
    nginx_dockerfile = (ROOT_DIR / "infra" / "docker" / "nginx" / "Dockerfile").read_text()

    assert backend_dockerfile.count("@sha256:") == 2
    assert nginx_dockerfile.count("@sha256:") == 1

    for compose_name in ("docker-compose.yml", "docker-compose.prod.yml"):
        compose = (ROOT_DIR / compose_name).read_text()
        assert "postgres:16-alpine@sha256:" in compose
        assert "redis:7-alpine@sha256:" in compose


def test_local_compose_cannot_inherit_production_django_settings():
    compose = (ROOT_DIR / "docker-compose.yml").read_text()

    assert compose.count("DJANGO_SETTINGS_MODULE: config.settings.dev") == 3
    assert "DJANGO_DEV_ALLOWED_HOSTS:-localhost,127.0.0.1,0.0.0.0" in compose
    assert "DJANGO_DEV_CSRF_TRUSTED_ORIGINS:-http://localhost:8080" in compose
    assert "DJANGO_DEV_PUBLIC_BASE_URL:-http://localhost:8080" in compose
    assert compose.count("image: prenium-dtf-backend-dev:${APP_IMAGE_TAG:-local}") == 3
    assert compose.count("dockerfile: infra/docker/backend/Dockerfile") == 1


def test_nginx_preserves_direct_http_scheme_without_proxy_header():
    nginx = (ROOT_DIR / "infra" / "nginx" / "default.conf").read_text()

    assert '""      $scheme;' in nginx
    assert '""      https;' not in nginx
