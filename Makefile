.PHONY: help up health agents-check check migrations-plan test test-ui test-orders test-b2b lint format audit shell logs-web logs-worker sync-frontend

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make up              Start local Docker services' \
		'  make sync-frontend   Build CSS, collectstatic, restart web' \
		'  make health          Check HTTP health endpoint' \
		'  make agents-check    Validate Codex agent contracts' \
		'  make check           Run Django system checks in Docker' \
		'  make migrations-plan Check pending Django migrations' \
		'  make test            Run pytest in Docker' \
		'  make test-ui         Run UI test subset in Docker' \
		'  make test-orders     Run orders and uploads tests in Docker' \
		'  make test-b2b        Run B2B order project tests in Docker' \
		'  make lint            Run ruff check in Docker' \
		'  make format          Run ruff format --check in Docker' \
		'  make audit           Run pip-audit in Docker' \
		'  make shell           Open Django shell in Docker' \
		'  make logs-web        Tail web container logs' \
		'  make logs-worker     Tail worker container logs'

up:
	docker compose up -d db redis web worker beat nginx

health:
	curl --fail --silent --show-error http://localhost:8080/healthz/

agents-check:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && python scripts/check_codex_agents.py'

check:
	docker compose exec web sh -lc 'cd /app/backend && python manage.py check'

migrations-plan:
	docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'

test:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'

test-ui:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui'

test-orders:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/orders tests/uploads'

test-b2b:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/b2b_order_projects backend/apps/portal/tests/test_ui_coherence.py'

lint:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'

format:
	docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'

audit:
	docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'

shell:
	docker compose exec web sh -lc 'cd /app/backend && python manage.py shell'

logs-web:
	docker compose logs --tail=200 web

logs-worker:
	docker compose logs --tail=200 worker

sync-frontend:
	cd backend && npm run build:css
	docker compose exec -T web sh -lc 'cd /app/backend && python manage.py collectstatic --noinput'
	docker compose restart web
