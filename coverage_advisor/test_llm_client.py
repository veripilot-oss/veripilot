"""Tests for coverage_advisor/llm_client.py.

Verifies:
- No API key (and non-local base URL) -> returns None and makes no HTTP request.
- Local base URL (e.g. Ollama at localhost or 127.0.0.1) allows requests without an API key.
- HTTP error (401, 500), connection error, timeout, malformed JSON -> returns None.
- Valid response -> parses OpenAI-compatible chat completions format and returns text.
- Environment variables: VERIPILOT_LLM_API_KEY, VERIPILOT_LLM_BASE_URL, VERIPILOT_LLM_MODEL.
- The API key never appears in any return value, stdout, or stderr.
- All tests use unittest.mock; no real network and no real API key.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coverage_advisor import llm_client


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        # Save original environment to avoid side effects
        self._orig_env = os.environ.copy()
        # Clean any preexisting LLM environment variables for test isolation
        for var in ("VERIPILOT_LLM_API_KEY", "VERIPILOT_LLM_BASE_URL", "VERIPILOT_LLM_MODEL", "ANTHROPIC_API_KEY"):
            os.environ.pop(var, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    # -----------------------------------------------------------------------
    # 1. No key -> None and no request made (with default/remote base URL)
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_no_key_returns_none_and_makes_no_request(self, mock_urlopen):
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_empty_key_returns_none_and_makes_no_request(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = ""
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_whitespace_key_returns_none_and_makes_no_request(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "   \t \n "
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_empty_or_whitespace_prompt_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-test-key-12345"
        self.assertIsNone(llm_client.complete(""))
        self.assertIsNone(llm_client.complete("   \n\t"))
        mock_urlopen.assert_not_called()

    # -----------------------------------------------------------------------
    # 2. Local base URL (Ollama / local server) without API key
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_local_base_url_allows_requests_without_key(self, mock_urlopen):
        """Ollama and local endpoints (http://localhost, http://127.0.0.1) need no key."""
        os.environ["VERIPILOT_LLM_BASE_URL"] = "http://localhost:11434/v1"
        # Notice: NO VERIPILOT_LLM_API_KEY set

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "// stimulus from local ollama"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus for spi")
        self.assertEqual(result, "// stimulus from local ollama")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:11434/v1/chat/completions")
        # No Authorization header should be set when key is omitted
        self.assertNotIn("Authorization", req.headers)
        self.assertNotIn("authorization", req.headers)

    @patch("urllib.request.urlopen")
    def test_local_127_0_0_1_allows_requests_without_key(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_BASE_URL"] = "http://127.0.0.1:8000/v1"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "// stimulus from 127.0.0.1"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus for timer")
        self.assertEqual(result, "// stimulus from 127.0.0.1")
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://127.0.0.1:8000/v1/chat/completions")

    # -----------------------------------------------------------------------
    # 3. Valid responses (OpenAI chat-completions format)
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_good_response_returns_content_string(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-test-key-12345"
        expected_verilog = "// Generated stimulus\n@(posedge clk); wr_en <= 1'b1;"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": expected_verilog,
                    },
                    "finish_reason": "stop"
                }
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus for fifo")
        self.assertEqual(result, expected_verilog)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, f"{llm_client.DEFAULT_BASE_URL}/chat/completions")
        self.assertEqual(req.headers.get("Authorization"), "Bearer sk-test-key-12345")
        self.assertEqual(req.headers.get("Content-type"), "application/json")

        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["model"], llm_client.DEFAULT_MODEL)
        self.assertEqual(payload["max_tokens"], llm_client.MAX_TOKENS)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Draft stimulus for fifo"}])

    @patch("urllib.request.urlopen")
    def test_good_response_with_multipart_content_list(self, mock_urlopen):
        """Test OpenAI / Gemini compat with content parts list: [{'type': 'text', 'text': '...'}]"""
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-test-key-12345"
        expected_verilog = "// Stimulus from content parts"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": expected_verilog}
                        ],
                    }
                }
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus for spi")
        self.assertEqual(result, expected_verilog)

    @patch("urllib.request.urlopen")
    def test_custom_model_environment_override(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-test-key-12345"
        os.environ["VERIPILOT_LLM_MODEL"] = "llama-3.3-70b-versatile"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "ok"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertEqual(result, "ok")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["model"], "llama-3.3-70b-versatile")

    # -----------------------------------------------------------------------
    # 4. Error handling (HTTP error, connection error, timeout, malformed JSON)
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_http_error_401_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "invalid-key"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=f"{llm_client.DEFAULT_BASE_URL}/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"message": "Invalid API key"}}'),
        )
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_http_error_500_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-key"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=f"{llm_client.DEFAULT_BASE_URL}/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"message": "Server error"}}'),
        )
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_network_connection_error_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-key"
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-key"
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        result = llm_client.complete("Draft stimulus", timeout=5.0)
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_malformed_json_response_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-key"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_missing_choices_or_empty_choices_returns_none(self, mock_urlopen):
        os.environ["VERIPILOT_LLM_API_KEY"] = "sk-key"
        for bad_payload in [{}, {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {}}]}]:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(bad_payload).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            result = llm_client.complete("Draft stimulus")
            self.assertIsNone(result)

    # -----------------------------------------------------------------------
    # 5. Security: The API key never appears in any return value or output
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_api_key_never_appears_in_return_value_or_output(self, mock_urlopen):
        secret_key = "sk-super-secret-production-key-98765"
        os.environ["VERIPILOT_LLM_API_KEY"] = secret_key

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Normal verilog output"}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            result = llm_client.complete("Draft stimulus")

        self.assertNotIn(secret_key, str(result))
        self.assertNotIn(secret_key, out_buf.getvalue())
        self.assertNotIn(secret_key, err_buf.getvalue())

    @patch("urllib.request.urlopen")
    def test_api_key_never_leaked_on_error(self, mock_urlopen):
        secret_key = "sk-confidential-token-55555"
        os.environ["VERIPILOT_LLM_API_KEY"] = secret_key
        mock_urlopen.side_effect = RuntimeError(f"Connection failure with {secret_key}")

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            result = llm_client.complete("Draft stimulus")

        self.assertIsNone(result)
        self.assertNotIn(secret_key, out_buf.getvalue())
        self.assertNotIn(secret_key, err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
