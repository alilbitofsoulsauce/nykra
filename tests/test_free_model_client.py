"""Tests of explicit free-endpoint inference without live network or credentials."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.free_model_client import FreeModelError, cli, generate


class Response:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=None):
        return self.body


def fake_response(text="def f(x): return x", cost=0, model="cohere/north-mini-code:free"):
    return {
        "id": "fake-response",
        "model": model,
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "cost": cost},
        "choices": [{"finish_reason": "stop", "message": {"content": text}}],
    }


class FreeModelTests(unittest.TestCase):
    def test_approval_required(self):
        with self.assertRaisesRegex(FreeModelError, "approval"):
            generate("hi", model="cohere/north-mini-code:free", token="mock")

    def test_paid_model_rejected_before_network(self):
        for model in ("openai/gpt-6", "openrouter/auto", "cohere/foo",
                      "openrouter/free", "cohere/north-mini-code:free;foo"):
            with self.subTest(model=model):
                with self.assertRaisesRegex(FreeModelError, "free route"):
                    generate("hi", model=model, token="mock", approve=True)

    def test_no_credential_fail_closed(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(FreeModelError, "API_KEY"):
                generate("hi", model="cohere/north-mini-code:free", approve=True)

    def test_short_empty_bad_limits(self):
        kwargs = {"model": "cohere/north-mini-code:free", "approve": True}
        for tokens in (1, 99999, 100.0):
            with self.subTest(tokens=tokens):
                with self.assertRaises(FreeModelError):
                    generate("hi", max_tokens=tokens, **kwargs)
        for timeout in (1, 181):
            with self.subTest(timeout=timeout):
                with self.assertRaises(FreeModelError):
                    generate("hi", timeout=timeout, **kwargs)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_valid_free_route_returns_content_and_receipt(self, opened):
        opened.return_value = Response(fake_response())
        result = generate("hi", model="cohere/north-mini-code:free",
                          token="test-secret", approve=True)
        self.assertEqual(result["text"], "def f(x): return x")
        self.assertEqual(result["receipt"]["cost"], 0)
        self.assertEqual(result["receipt"]["model"], "cohere/north-mini-code:free")
        self.assertNotIn("test-secret", str(result))
        request = opened.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(sent["model"], "cohere/north-mini-code:free")
        self.assertFalse(sent["provider"]["allow_fallbacks"])
        self.assertFalse(sent["reasoning"]["enabled"])
        self.assertEqual(sent["stream"], False)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_nonzero_cost_fails_closed(self, opened):
        opened.return_value = Response(fake_response(cost=0.01))
        with self.assertRaisesRegex(FreeModelError, "nonzero"):
            generate("hi", model="cohere/north-mini-code:free", token="mock", approve=True)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_empty_reasoning_only_is_not_a_proposal(self, opened):
        opened.return_value = Response(fake_response(text=""))
        with self.assertRaisesRegex(FreeModelError, "reasoning-only"):
            generate("hi", model="cohere/north-mini-code:free", token="mock", approve=True)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_model_identity_change_rejected(self, opened):
        opened.return_value = Response(fake_response(model="cohere/paid"))
        with self.assertRaisesRegex(FreeModelError, "model identity"):
            generate("hi", model="cohere/north-mini-code:free", token="mock", approve=True)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_timeout_redacted(self, opened):
        opened.side_effect = TimeoutError("sensitive token not to be printed")
        with self.assertRaises(FreeModelError) as raised:
            generate("hi", model="cohere/north-mini-code:free", token="mock", approve=True)
        self.assertNotIn("sensitive token", str(raised.exception))

    @patch("nykra.free_model_client.generate")
    def test_cli_writes_one_model_proposal_only(self, generate_mock):
        generate_mock.return_value = {"text": "x = 7\n", "receipt": {"cost": 0}}
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            prompt, out = home / "prompt.txt", home / "candidate.py"
            prompt.write_text("Return x = 7", encoding="utf-8")
            args = ["--model", "cohere/north-mini-code:free",
                    "--prompt-file", str(prompt), "--output-file", str(out), "--approve"]
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cli(args), 0)
                self.assertEqual(out.read_text(encoding="utf-8"), "x = 7\n")
                self.assertEqual(cli(args), 2)
            self.assertEqual(generate_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
