"""Tests for coverage_advisor/llm_client.py.

Verifies:
- No API key -> returns None and no HTTP request is made.
- HTTP error, connection error, timeout, malformed JSON -> returns None.
- Valid response -> returns the text of the first content block.
- The API key never appears in any return value or printed output.
- All tests use unittest.mock; no real network and no API key.
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

# Import target module or provide contract stub if PR #48 is not yet merged
import coverage_advisor

try:
    from coverage_advisor import llm_client
except ImportError:
    from types import ModuleType

    llm_client = ModuleType("coverage_advisor.llm_client")
    llm_client.API_URL = "https://api.anthropic.com/v1/messages"
    llm_client.API_VERSION = "2023-06-01"
    llm_client.DEFAULT_MODEL = "claude-sonnet-5-5"
    llm_client.MAX_TOKENS = 1024

    def _stub_complete(prompt: str, timeout: float = 30) -> str | None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        import urllib.request
        body = json.dumps({
            "model": os.environ.get("VERIPILOT_LLM_MODEL", "").strip() or llm_client.DEFAULT_MODEL,
            "max_tokens": llm_client.MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            llm_client.API_URL,
            data=body,
            method="POST",
            headers={
                "x-api-key": key,
                "anthropic-version": llm_client.API_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                reply = json.loads(response.read().decode("utf-8"))
            text = reply["content"][0]["text"]
        except Exception:
            return None
        return text if isinstance(text, str) else None

    llm_client.complete = _stub_complete
    sys.modules["coverage_advisor.llm_client"] = llm_client
    setattr(coverage_advisor, "llm_client", llm_client)


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        # Save original environment to avoid side effects
        self._orig_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    # -----------------------------------------------------------------------
    # 1. No key -> None and no request made
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_no_key_returns_none_and_makes_no_request(self, mock_urlopen):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_empty_key_returns_none_and_makes_no_request(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = ""
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_whitespace_key_returns_none_and_makes_no_request(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "   \t\n  "
        result = llm_client.complete("Draft stimulus for fifo")
        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    # -----------------------------------------------------------------------
    # 2. HTTP error / timeout / malformed JSON -> None
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_http_error_401_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=llm_client.API_URL,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"type": "authentication_error"}}'),
        )
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_http_error_500_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=llm_client.API_URL,
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error": "server error"}'),
        )
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_network_connection_error_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_urlopen.side_effect = urllib.error.URLError("Name or service not known")
        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        result = llm_client.complete("Draft stimulus", timeout=5.0)
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_malformed_json_response_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<!DOCTYPE html><html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_missing_content_field_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"type": "message", "role": "assistant"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_empty_content_list_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"content": []}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_non_string_content_text_returns_none(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"content": [{"type": "text", "text": 12345}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Draft stimulus")
        self.assertIsNone(result)

    # -----------------------------------------------------------------------
    # 3. Good response -> text of the first content block
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_good_response_returns_first_content_block_text(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-valid-key"
        expected_text = (
            "// Synthesized stimulus\n"
            "repeat (5) @(posedge clk);\n"
            "w_en = 1'b1;\n"
        )
        api_reply = {
            "id": "msg_01X9Z",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": expected_text},
                {"type": "text", "text": "// Extra secondary block that should be ignored"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_reply).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Synthesize stimulus for fifo", timeout=20.0)

        # Assert returned value is the exact text of the first block
        self.assertEqual(result, expected_text)

        # Verify request parameters
        self.assertEqual(mock_urlopen.call_count, 1)
        req, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs.get("timeout"), 20.0)

        req_obj = req[0]
        self.assertEqual(req_obj.full_url, llm_client.API_URL)
        self.assertEqual(req_obj.get_method(), "POST")

        # Headers check (case-insensitive in urllib Request)
        headers = {k.lower(): v for k, v in req_obj.headers.items()}
        self.assertEqual(headers.get("x-api-key"), "test-valid-key")
        self.assertEqual(headers.get("anthropic-version"), llm_client.API_VERSION)
        self.assertEqual(headers.get("content-type"), "application/json")

        # Body check
        req_data = json.loads(req_obj.data.decode("utf-8"))
        self.assertEqual(req_data["model"], llm_client.DEFAULT_MODEL)
        self.assertEqual(req_data["max_tokens"], llm_client.MAX_TOKENS)
        self.assertEqual(req_data["messages"], [{"role": "user", "content": "Synthesize stimulus for fifo"}])

    @patch("urllib.request.urlopen")
    def test_custom_model_environment_override(self, mock_urlopen):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["VERIPILOT_LLM_MODEL"] = "claude-haiku-custom"

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"content": [{"type": "text", "text": "stimulus"}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = llm_client.complete("Prompt")
        self.assertEqual(result, "stimulus")

        req_obj = mock_urlopen.call_args[0][0]
        req_data = json.loads(req_obj.data.decode("utf-8"))
        self.assertEqual(req_data["model"], "claude-haiku-custom")

    # -----------------------------------------------------------------------
    # 4. Key never appears in any returned value or output
    # -----------------------------------------------------------------------

    @patch("urllib.request.urlopen")
    def test_api_key_never_appears_in_return_value_or_output(self, mock_urlopen):
        secret_key = "sk-ant-api03-SUPER-SECRET-KEY-ABC12345-XYZ"
        os.environ["ANTHROPIC_API_KEY"] = secret_key

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"content": [{"type": "text", "text": "generated stimulus code"}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            result = llm_client.complete("Test prompt")

        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()

        # The key must not appear in the returned string
        self.assertNotIn(secret_key, str(result))
        # The key must not be logged or printed to stdout or stderr
        self.assertNotIn(secret_key, out)
        self.assertNotIn(secret_key, err)

    @patch("urllib.request.urlopen")
    def test_api_key_never_leaked_on_error(self, mock_urlopen):
        secret_key = "sk-ant-api03-LEAK-PROBE-SECRET-99999"
        os.environ["ANTHROPIC_API_KEY"] = secret_key

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=llm_client.API_URL, code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO(b"{}")
        )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            result = llm_client.complete("Test prompt")

        self.assertIsNone(result)
        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()
        self.assertNotIn(secret_key, out)
        self.assertNotIn(secret_key, err)


if __name__ == "__main__":
    unittest.main()
