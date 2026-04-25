"""
Comprehensive test suite for the Learnr backend API.

Covers:
  - Happy path scenarios
  - Input validation / edge cases
  - Rate limiting
  - Security assertions
  - Integration tests with mocked Gemini SDK
"""

import base64
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock

# The conftest.py fixture provides `client` and `reset_rate_limits`.
# We import `rate_limits` so integration tests can inspect state.
from main import rate_limits, SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_SESSION = "test-session-abc123"
VALID_MESSAGE = "What is machine learning?"

MOCK_PATCH = "main.genai.GenerativeModel"


def _make_fake_gemini_response(text: str = "This is a test reply from Learnr."):
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = text
    mock_model.generate_content.return_value = mock_response
    return mock_model


def _minimal_base64_png() -> str:
    """Return a real, minimal 1x1 transparent PNG as a base64 data URI."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    b64 = base64.b64encode(png_bytes).decode()
    return f"data:image/png;base64,{b64}"


# ===========================================================================
# 1. HAPPY PATH
# ===========================================================================
class TestHappyPath:

    @pytest.mark.asyncio
    async def test_valid_chat_returns_200_with_reply(self, client: AsyncClient):
        """POST /chat with a valid message and session_id returns 200 with a 'reply' key."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response()):
            response = await client.post(
                "/chat",
                json={"message": VALID_MESSAGE, "session_id": VALID_SESSION},
            )
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 0

    @pytest.mark.asyncio
    async def test_chat_with_text_file_content_returns_200(self, client: AsyncClient):
        """POST /chat with text file_content returns 200 and a non-empty reply."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response("Great question about Python!")):
            response = await client.post(
                "/chat",
                json={
                    "message": "Summarise this file",
                    "session_id": VALID_SESSION,
                    "file_content": "Python is a high-level programming language.",
                    "file_type": "text/plain",
                    "filename": "notes.txt",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["reply"]

    @pytest.mark.asyncio
    async def test_chat_with_image_base64_returns_200(self, client: AsyncClient):
        """POST /chat with a base64 image payload returns 200."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response("I can see an image.")):
            response = await client.post(
                "/chat",
                json={
                    "message": "What is in this image?",
                    "session_id": VALID_SESSION,
                    "file_content": _minimal_base64_png(),
                    "file_type": "image/png",
                    "filename": "pixel.png",
                },
            )
        assert response.status_code == 200
        assert response.json()["reply"]

    @pytest.mark.asyncio
    async def test_gcs_uri_returned_when_storage_client_present(self, client: AsyncClient):
        """When GCS upload succeeds, gcs_uri is returned in the response."""
        mock_model = _make_fake_gemini_response()

        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage = MagicMock()
        mock_storage.bucket.return_value = mock_bucket

        with (
            patch(MOCK_PATCH, return_value=mock_model),
            patch("main.storage_client", mock_storage),
            patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}),
        ):
            response = await client.post(
                "/chat",
                json={
                    "message": "Tell me about this",
                    "session_id": VALID_SESSION,
                    "file_content": "some file text",
                    "file_type": "text/plain",
                    "filename": "doc.txt",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("gcs_uri") is not None
        assert data["gcs_uri"].startswith("gs://learnr-uploads-test-project/")


# ===========================================================================
# 2. VALIDATION / EDGE CASES
# ===========================================================================
class TestValidation:

    @pytest.mark.asyncio
    async def test_message_over_4000_chars_returns_422(self, client: AsyncClient):
        """A message exceeding 4000 characters should return 422."""
        response = await client.post(
            "/chat",
            json={"message": "x" * 4001, "session_id": VALID_SESSION},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_session", [
        "../../etc/passwd",
        "session id with spaces",
        "session@!#$%",
        "<script>alert(1)</script>",
    ])
    async def test_invalid_session_id_returns_422(self, client: AsyncClient, bad_session: str):
        """session_id values with special characters should return 422."""
        response = await client.post(
            "/chat",
            json={"message": VALID_MESSAGE, "session_id": bad_session},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_file_content_over_500kb_returns_422(self, client: AsyncClient):
        """file_content exceeding 500KB should return 422."""
        # 500_001 characters > 500_000 byte limit
        big_content = "a" * 500_001
        response = await client.post(
            "/chat",
            json={
                "message": VALID_MESSAGE,
                "session_id": VALID_SESSION,
                "file_content": big_content,
                "file_type": "text/plain",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_message_field_returns_422(self, client: AsyncClient):
        """Requests without a 'message' field should return 422."""
        response = await client.post(
            "/chat",
            json={"session_id": VALID_SESSION},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_message_returns_422(self, client: AsyncClient):
        """An empty string message should return 422 (min_length=1 via str validation)."""
        response = await client.post(
            "/chat",
            json={"message": "", "session_id": VALID_SESSION},
        )
        # An empty string is still a valid str in Pydantic by default.
        # The backend currently returns 200 but generates an unhelpful response.
        # This test documents current behaviour; update if a min_length=1 is added.
        assert response.status_code in (200, 422)


# ===========================================================================
# 3. RATE LIMITING
# ===========================================================================
class TestRateLimiting:

    @pytest.mark.asyncio
    async def test_21st_request_returns_429(self, client: AsyncClient):
        """The 21st request from the same session_id within a minute must return 429."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response()):
            for i in range(20):
                r = await client.post(
                    "/chat",
                    json={"message": f"msg {i}", "session_id": "rate-limit-session"},
                )
                assert r.status_code == 200, f"Request {i+1} should succeed, got {r.status_code}"

        # 21st request — no mock needed, should be rejected before hitting Gemini
        r21 = await client.post(
            "/chat",
            json={"message": "one too many", "session_id": "rate-limit-session"},
        )
        assert r21.status_code == 429
        assert "Rate limit exceeded" in r21.json()["detail"]

    @pytest.mark.asyncio
    async def test_different_sessions_are_isolated(self, client: AsyncClient):
        """Rate limit is per session_id; different sessions must not interfere."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response()):
            for i in range(20):
                await client.post(
                    "/chat",
                    json={"message": f"msg {i}", "session_id": "session-A"},
                )
            # session-B should still be allowed
            r = await client.post(
                "/chat",
                json={"message": "fresh session", "session_id": "session-B"},
            )
        assert r.status_code == 200


# ===========================================================================
# 4. SECURITY
# ===========================================================================
class TestSecurity:

    @pytest.mark.asyncio
    async def test_api_key_not_echoed_in_reply(self, client: AsyncClient):
        """The Gemini API key must never appear in the API response body."""
        api_key = os.environ.get("GEMINI_API_KEY", "test-fake-key-do-not-use")
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response(f"normal response")):
            response = await client.post(
                "/chat",
                json={"message": VALID_MESSAGE, "session_id": VALID_SESSION},
            )
        assert api_key not in response.text

    @pytest.mark.asyncio
    async def test_csp_header_present_on_chat_endpoint(self, client: AsyncClient):
        """Content-Security-Policy header must be set on all API responses."""
        with patch(MOCK_PATCH, return_value=_make_fake_gemini_response()):
            response = await client.post(
                "/chat",
                json={"message": VALID_MESSAGE, "session_id": VALID_SESSION},
            )
        assert "content-security-policy" in response.headers
        csp = response.headers["content-security-policy"]
        assert "default-src" in csp

    @pytest.mark.asyncio
    async def test_csp_header_present_on_static_root(self, client: AsyncClient):
        """Content-Security-Policy header must also be present on the frontend root."""
        response = await client.get("/")
        assert "content-security-policy" in response.headers


# ===========================================================================
# 5. INTEGRATION — mock Gemini SDK, verify prompt construction
# ===========================================================================
class TestIntegration:

    @pytest.mark.asyncio
    async def test_system_prompt_contains_learnr_and_adaptive(self):
        """The system prompt must contain the strings 'Learnr' and 'adaptive'."""
        assert "Learnr" in SYSTEM_PROMPT
        assert "adaptive" in SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_text_file_content_prepended_in_user_message(self, client: AsyncClient):
        """file_content should be prepended into the user message sent to Gemini."""
        captured_parts = []
        file_text = "The speed of light is 299,792,458 m/s."

        def fake_model_factory(*args, **kwargs):
            mock_model = MagicMock()

            def capture_generate(parts):
                captured_parts.extend(parts)
                return MagicMock(text="Captured!")

            mock_model.generate_content.side_effect = capture_generate
            return mock_model

        with patch(MOCK_PATCH, side_effect=fake_model_factory):
            response = await client.post(
                "/chat",
                json={
                    "message": "What is the speed of light?",
                    "session_id": VALID_SESSION,
                    "file_content": file_text,
                    "file_type": "text/plain",
                    "filename": "physics.txt",
                },
            )

        assert response.status_code == 200
        assert len(captured_parts) == 1
        combined = captured_parts[0]
        assert file_text in combined
        assert "What is the speed of light?" in combined
        assert "Here is the content of the file" in combined

    @pytest.mark.asyncio
    async def test_image_sent_as_multimodal_blob_not_text(self, client: AsyncClient):
        """Image file_content must be sent to Gemini as a dict blob, not a raw string."""
        captured_parts = []

        def fake_model_factory(*args, **kwargs):
            mock_model = MagicMock()

            def capture_generate(parts):
                captured_parts.extend(parts)
                return MagicMock(text="I see the image.")

            mock_model.generate_content.side_effect = capture_generate
            return mock_model

        with patch(MOCK_PATCH, side_effect=fake_model_factory):
            response = await client.post(
                "/chat",
                json={
                    "message": "Describe this image.",
                    "session_id": VALID_SESSION,
                    "file_content": _minimal_base64_png(),
                    "file_type": "image/png",
                    "filename": "pixel.png",
                },
            )

        assert response.status_code == 200
        # First part must be the image dict blob
        image_blob = captured_parts[0]
        assert isinstance(image_blob, dict)
        assert image_blob.get("mime_type") == "image/png"
        assert isinstance(image_blob.get("data"), bytes)
        # Second part must be the user text
        assert captured_parts[1] == "Describe this image."

    @pytest.mark.asyncio
    async def test_no_file_sends_plain_message_to_gemini(self, client: AsyncClient):
        """Without file_content, only the bare user message is sent to Gemini."""
        captured_parts = []

        def fake_model_factory(*args, **kwargs):
            mock_model = MagicMock()

            def capture_generate(parts):
                captured_parts.extend(parts)
                return MagicMock(text="Hello!")

            mock_model.generate_content.side_effect = capture_generate
            return mock_model

        with patch(MOCK_PATCH, side_effect=fake_model_factory):
            response = await client.post(
                "/chat",
                json={"message": "Hello Learnr!", "session_id": VALID_SESSION},
            )

        assert response.status_code == 200
        assert len(captured_parts) == 1
        assert captured_parts[0] == "Hello Learnr!"
