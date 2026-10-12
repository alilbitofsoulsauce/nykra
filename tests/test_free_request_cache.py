"""Exact free-model request reuse: no network calls on authenticated cache hits."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nykra.free_model_client import FreeModelError, cli, generate_cached
from tests.test_free_model_client import Response, fake_response

MODEL = "cohere/north-mini-code:free"


class ExactFreeRequestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="nykra-free-cache-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.cache = self.home / "cache"
        self.args = {"model": MODEL, "cache_dir": self.cache,
                     "token": "high-entropy-test-account-one", "approve": True}

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_live_code_first_miss_second_exact_hit_skips_network(self, network):
        network.return_value = Response(fake_response("def solved(x): return x + 1"))
        first = generate_cached("Return correct Python", **self.args)
        second = generate_cached("Return correct Python", **self.args)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(first["text"], second["text"])
        self.assertFalse(first["receipt"]["cache_hit"])
        self.assertTrue(first["receipt"]["cache_saved"])
        self.assertEqual(first["receipt"]["provider_tokens_this_request"], 20)
        self.assertTrue(second["receipt"]["cache_hit"])
        self.assertFalse(second["receipt"]["provider_called_this_request"])
        self.assertEqual(second["receipt"]["provider_tokens_this_request"], 0)
        self.assertEqual(second["receipt"]["cost_this_request"], 0)
        self.assertEqual(second["receipt"]["provider_calls_avoided"], 1)
        self.assertEqual(second["receipt"]["tokens"]["prompt_tokens"], 12)
        self.assertEqual(len(list(self.cache.glob("*.json"))), 1)
        saved = next(self.cache.glob("*.json")).read_text(encoding="utf-8")
        self.assertNotIn("Return correct Python", saved)
        self.assertNotIn(self.args["token"], saved)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_different_prompt_not_equal_even_if_provider_output_same(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt v1", **self.args)
        generate_cached("prompt v2", **self.args)
        self.assertEqual(network.call_count, 2)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_changed_generation_limit_must_call_provider_again(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", max_tokens=400, **self.args)
        generate_cached("prompt", max_tokens=500, **self.args)
        self.assertEqual(network.call_count, 2)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_account_separation_uses_api_key_hmac_without_storing_it(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        generate_cached("prompt", **{**self.args, "token": "different-account-key"})
        self.assertEqual(network.call_count, 2)
        self.assertEqual(len(list(self.cache.glob("*.json"))), 2)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_invalid_cache_record_blocks_provider_call(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        saved = next(self.cache.glob("*.json"))
        saved.write_text("{invalid json!", encoding="utf-8")
        with self.assertRaisesRegex(FreeModelError, "integrity"):
            generate_cached("prompt", **self.args)
        self.assertEqual(network.call_count, 1)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_tampering_content_and_hash_both_detected_by_signature(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        p = next(self.cache.glob("*.json"))
        old = json.loads(p.read_text(encoding="utf-8"))
        old["text"] = "print('injected')"
        import hashlib
        old["receipt"]["sha256"] = hashlib.sha256(old["text"].encode()).hexdigest()
        p.write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(FreeModelError, "integrity"):
            generate_cached("prompt", **self.args)
        network.assert_called_once()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_provider_missing_cost_returns_content_but_refuses_cache_save(self, network):
        d = fake_response()
        d["usage"].pop("cost")
        network.return_value = Response(d)
        first = generate_cached("prompt", **self.args)
        second = generate_cached("prompt", **self.args)
        self.assertFalse(first["receipt"]["cache_saved"])
        self.assertFalse(second["receipt"]["cache_hit"])
        self.assertEqual(network.call_count, 2)
        self.assertEqual(list(self.cache.glob("*.json")), [])

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_provider_nonzero_cost_not_cached_and_request_fails(self, network):
        network.return_value = Response(fake_response(cost=0.01))
        with self.assertRaisesRegex(FreeModelError, "nonzero"):
            generate_cached("prompt", **self.args)
        self.assertEqual(list(self.cache.glob("*.json")), [])

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_bad_model_cannot_call_network_or_read_cache(self, network):
        with self.assertRaisesRegex(FreeModelError, "free route"):
            generate_cached("prompt", **{**self.args, "model": "openai/gpt-6"})
        network.assert_not_called()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_approval_checked_even_when_cache_is_populated(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        with self.assertRaisesRegex(FreeModelError, "approval"):
            generate_cached("prompt", **{**self.args, "approve": False})
        network.assert_called_once()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_api_key_required_even_to_replay(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(FreeModelError, "API_KEY"):
                generate_cached("prompt", model=MODEL, cache_dir=self.cache,
                                approve=True)
        network.assert_called_once()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_timeout_parameter_not_changing_model_payload_reuses_same_result(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", timeout=20, **self.args)
        second = generate_cached("prompt", timeout=100, **self.args)
        self.assertTrue(second["receipt"]["cache_hit"])
        network.assert_called_once()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_independent_cache_directory_does_not_cross_reuse(self, network):
        network.return_value = Response(fake_response())
        generate_cached("prompt", **self.args)
        generate_cached("prompt", **{**self.args, "cache_dir": self.home / "other"})
        self.assertEqual(network.call_count, 2)

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_cli_exact_cache_saves_two_proposals_with_one_actual_request(self, network):
        network.return_value = Response(fake_response("def add(a,b): return a+b"))
        prompt = self.home / "input.txt"
        prompt.write_text("Implement addition", encoding="utf-8")
        common = ["--model", MODEL, "--prompt-file", str(prompt),
                  "--cache-dir", str(self.cache),
                  "--reuse-exact-request", "--approve"]
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": self.args["token"]}):
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(cli([*common,"--output-file",str(self.home/"first.py")]), 0)
                self.assertFalse(json.loads(stdout.getvalue())["cache_hit"])
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(cli([*common,"--output-file",str(self.home/"second.py")]), 0)
                self.assertTrue(json.loads(stdout.getvalue())["cache_hit"])
        network.assert_called_once()
        self.assertEqual((self.home/"first.py").read_bytes(),
                         (self.home/"second.py").read_bytes())

    def test_cli_requires_both_optin_fields_and_does_not_call_provider(self):
        p = self.home / "input.txt"
        p.write_text("Code", encoding="utf-8")
        bare = ["--model", MODEL, "--prompt-file", str(p), "--output-file",
                str(self.home / "proposal.py"), "--approve"]
        with patch("nykra.free_model_client.generate") as inference:
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cli([*bare,"--reuse-exact-request"]), 2)
                self.assertEqual(cli([*bare,"--cache-dir",str(self.cache)]), 2)
            inference.assert_not_called()

    @patch("nykra.free_model_client.urllib.request.urlopen")
    def test_symlinked_cache_root_rejected(self, network):
        true_dir = self.home / "real"
        true_dir.mkdir()
        link = self.home / "cache-link"
        try:
            link.symlink_to(true_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("creating symlinks not authorized on this OS")
        with self.assertRaisesRegex(FreeModelError, "symbolic link"):
            generate_cached("prompt", **{**self.args, "cache_dir": link})
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
