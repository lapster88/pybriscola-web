import pytest


def _needs_django_fixtures(item):
    """Check if a test item needs Django-related fixtures."""
    # Tests in test_cli_repl.py don't need Django fixtures
    if "test_cli_repl" in str(item.fspath):
        return False
    return True


@pytest.fixture(autouse=True)
def in_memory_channel_layer(request):
    # Skip this fixture for tests that don't need Django
    if not _needs_django_fixtures(request.node):
        yield
        return
    # For unit tests, use in-memory channel layer; for integration, keep real redis
    import os
    from django.conf import settings
    if os.getenv("INTEGRATION_E2E") == "1":
        yield
    else:
        settings.CHANNEL_LAYERS = {
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        }
        yield


@pytest.fixture(autouse=True)
def clear_active_connections(request):
    # Skip this fixture for tests that don't need Django
    if not _needs_django_fixtures(request.node):
        yield
        return
    from briscola import consumers
    consumers.ACTIVE_CONNECTIONS.clear()
    yield
    consumers.ACTIVE_CONNECTIONS.clear()
