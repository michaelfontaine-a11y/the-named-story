"""Verify both API entrypoints reject missing credentials before any work."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent


def load_app(path):
    spec = importlib.util.spec_from_file_location("tested_app", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuthenticationTests(unittest.TestCase):
    def test_missing_or_blank_secret_prevents_startup(self):
        for path in ("app.py", "files/app.py"):
            for value in (None, "", "   "):
                with self.subTest(path=path, value=value):
                    with patch.dict(os.environ, {}, clear=True):
                        if value is not None:
                            os.environ["API_SECRET"] = value
                        with self.assertRaisesRegex(RuntimeError, "API_SECRET must be set"):
                            load_app(path)

    def test_authentication_precedes_generation(self):
        for path in ("app.py", "files/app.py"):
            with self.subTest(path=path):
                with patch.dict(os.environ, {"API_SECRET": "unit-test-only"}, clear=True):
                    module = load_app(path)
                client = module.app.test_client()
                with patch.object(module, "get_r2_client", side_effect=AssertionError("Unexpected R2 call")):
                    self.assertEqual(client.get("/health").status_code, 200)
                    for authorization in (None, "Bearer wrong", "Bearer "):
                        headers = {} if authorization is None else {"Authorization": authorization}
                        response = client.post("/generate", json={"name": "Test"}, headers=headers)
                        self.assertEqual(response.status_code, 401)
                    response = client.post("/generate", json={}, headers={"Authorization": "Bearer unit-test-only"})
                    self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
