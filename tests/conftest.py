import pytest


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    # For unit tests, use in-memory channel layer; for integration, keep real redis
    import os
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
def clear_active_connections():
    from briscola import consumers
    consumers.ACTIVE_CONNECTIONS.clear()
    yield
    consumers.ACTIVE_CONNECTIONS.clear()
