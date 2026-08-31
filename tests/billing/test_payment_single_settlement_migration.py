from importlib import import_module
from unittest.mock import Mock

import pytest


def _historical_apps(*, duplicate_settlement: bool, ambiguous_capture: bool):
    financial_statuses = Mock()
    duplicate_exists = (
        financial_statuses.values.return_value.annotate.return_value.filter.return_value.exists
    )
    duplicate_exists.return_value = duplicate_settlement
    ambiguous_rows = Mock()
    ambiguous_rows.exists.return_value = ambiguous_capture
    payment_model = Mock()
    payment_model.objects.filter.side_effect = [financial_statuses, ambiguous_rows]
    apps = Mock()
    apps.get_model.return_value = payment_model
    return apps


def test_payment_single_settlement_migration_accepts_clean_history():
    migration = import_module("apps.billing.migrations.0009_payment_single_settlement")

    migration.validate_existing_payment_settlements(
        _historical_apps(duplicate_settlement=False, ambiguous_capture=False),
        schema_editor=None,
    )


def test_payment_single_settlement_migration_rejects_duplicate_settlements():
    migration = import_module("apps.billing.migrations.0009_payment_single_settlement")

    with pytest.raises(RuntimeError, match="plusieurs captures financières"):
        migration.validate_existing_payment_settlements(
            _historical_apps(duplicate_settlement=True, ambiguous_capture=False),
            schema_editor=None,
        )


def test_payment_single_settlement_migration_rejects_ambiguous_capture_ids():
    migration = import_module("apps.billing.migrations.0009_payment_single_settlement")

    with pytest.raises(RuntimeError, match="identifiant de capture"):
        migration.validate_existing_payment_settlements(
            _historical_apps(duplicate_settlement=False, ambiguous_capture=True),
            schema_editor=None,
        )
