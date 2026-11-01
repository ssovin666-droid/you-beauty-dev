"""Dependency-free regression test of the actual client creation guard."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class AnalyticsGateTest(unittest.TestCase):
    def test_environment_matrix(self):
        path = Path(__file__).parents[1] / 'app/core/amplitude.py'
        tree = ast.parse(path.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_amplitude_client')
        fn.returns = None
        code = compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec')
        for env in ['staging', 'development', 'production']:
            for enabled in [False, True]:
                for key in ['', 'test-key']:
                    with self.subTest(env=env, enabled=enabled, key=key):
                        clients = []
                        def create_client(key):
                            client = object()
                            clients.append(client)
                            return client
                        scope = dict(settings=SimpleNamespace(app_env=env, analytics_enabled=enabled, amplitude_api_key=key), _client=None, Amplitude=create_client)
                        exec(code, scope)
                        result = scope['get_amplitude_client']()
                        self.assertEqual(result is not None, env == 'production' and enabled and bool(key))
                        self.assertIs(result, scope['get_amplitude_client']())
                        self.assertLessEqual(len(clients), 1)


if __name__ == '__main__':
    unittest.main()
