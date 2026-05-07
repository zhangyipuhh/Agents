import pytest
from app.core.agent.AgentContext import AgentContext


class TestAgentContext:
    def test_default_values(self):
        ctx = AgentContext()
        assert ctx.get("session_id", "default") == "default"
        assert ctx.get("namespace", {}) == {}
        assert ctx.get("store_id", "default") == "default"
        assert ctx.get("image_ids", []) == []
        assert ctx.get("host_session_id") is None

    def test_custom_values(self):
        ctx = AgentContext(
            session_id="test-session-123",
            store_id="store-456",
            image_ids=["img1", "img2"],
            host_session_id="host-789",
        )
        assert ctx["session_id"] == "test-session-123"
        assert ctx["store_id"] == "store-456"
        assert ctx["image_ids"] == ["img1", "img2"]
        assert ctx["host_session_id"] == "host-789"

    def test_is_typed_dict(self):
        assert hasattr(AgentContext, "__annotations__")
        expected_keys = {"session_id", "namespace", "store_id", "image_ids", "host_session_id"}
        assert set(AgentContext.__annotations__.keys()) == expected_keys

    def test_annotation_types(self):
        annotations = AgentContext.__annotations__
        assert annotations["session_id"] is str
        assert annotations["store_id"] is str
        assert annotations["image_ids"] == list[str]

    def test_session_id_field_exists(self):
        ctx = AgentContext(session_id="custom-id")
        assert ctx["session_id"] == "custom-id"

    def test_host_session_id_optional(self):
        ctx1 = AgentContext()
        assert ctx1.get("host_session_id") is None

        ctx2 = AgentContext(host_session_id="host-123")
        assert ctx2["host_session_id"] == "host-123"
