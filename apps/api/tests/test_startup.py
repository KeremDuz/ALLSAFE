import pytest
from fastapi.testclient import TestClient

from allsafe_api.main import create_app


def test_readiness_rejects_database_without_required_schema(settings):
    settings.initialize_schema = False
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_bootstrap_authentication_cannot_start_in_production(settings):
    settings.environment = "production"
    with pytest.raises(RuntimeError, match="Production"):
        with TestClient(create_app(settings)):
            pytest.fail("Production startup unexpectedly accepted bootstrap authentication")
