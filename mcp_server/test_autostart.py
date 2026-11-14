import unittest
from pathlib import Path
from unittest import mock
import urllib.error

import server as mcp


class SigmaAutostartTests(unittest.TestCase):
    def setUp(self):
        self.workspace = str(Path.cwd())
        mcp._sigma_process = None

    def tearDown(self):
        mcp._sigma_process = None

    def test_ready_existing_sigma_is_activated_without_spawning(self):
        calls = []

        def request(method, route, body=None, timeout=3):
            calls.append((method, route, body))
            return {"success": True, "ready": True, "workspace_path": self.workspace}

        with mock.patch.object(mcp, "control_request", side_effect=request), \
             mock.patch.object(mcp.subprocess, "Popen") as popen:
            mcp.activate_sigma(self.workspace)

        popen.assert_not_called()
        self.assertEqual([c[1] for c in calls], ["/mcp/status", "/mcp/activate"])
        self.assertEqual(calls[-1][2], {"workspace_path": self.workspace})

    def test_startup_in_progress_waits_instead_of_spawning_duplicate(self):
        calls = []
        responses = iter([
            {"success": True, "ready": False},
            {"success": True, "ready": True},
            {"success": True, "workspace_path": self.workspace},
        ])

        def request(method, route, body=None, timeout=3):
            calls.append(route)
            return next(responses)

        with mock.patch.object(mcp, "control_request", side_effect=request), \
             mock.patch.object(mcp.subprocess, "Popen") as popen, \
             mock.patch.object(mcp.time, "sleep"):
            mcp.activate_sigma(self.workspace)

        popen.assert_not_called()
        self.assertEqual(calls, ["/mcp/status", "/mcp/status", "/mcp/activate"])

    def test_closed_sigma_launches_electron_dev_and_keeps_logs_off_stdout(self):
        calls = []
        responses = iter([
            urllib.error.URLError("closed"),
            {"success": True, "ready": True},
            {"success": True, "workspace_path": self.workspace},
        ])

        def request(method, route, body=None, timeout=3):
            calls.append(route)
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        child = mock.Mock()
        child.poll.return_value = None
        with mock.patch.object(mcp, "PROJECT_DIR", Path.cwd()), \
             mock.patch.object(mcp, "control_request", side_effect=request), \
             mock.patch.object(mcp.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(mcp.time, "sleep"):
            mcp.activate_sigma(self.workspace)

        self.assertEqual(popen.call_args.args[0][-2:], ["run", "electron:dev"])
        self.assertEqual(popen.call_args.kwargs["cwd"], Path.cwd())
        self.assertIs(popen.call_args.kwargs["stdout"], __import__("sys").stderr)
        self.assertIs(popen.call_args.kwargs["stderr"], __import__("sys").stderr)
        self.assertEqual(calls, ["/mcp/status", "/mcp/status", "/mcp/activate"])

    def test_missing_project_fails_before_spawning(self):
        with mock.patch.object(mcp, "PROJECT_DIR", Path.cwd() / "missing-sigma-project"), \
             mock.patch.object(mcp, "control_request", side_effect=urllib.error.URLError("closed")), \
             mock.patch.object(mcp.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "SIGMA_PROJECT_DIR"):
                mcp.ensure_sigma_started()
        popen.assert_not_called()

    def test_mcp_initialize_response_remains_json_rpc(self):
        message = {"jsonrpc": "2.0", "id": 5, "method": "initialize", "params": {}}
        with mock.patch.object(mcp.sys, "stdout") as stdout:
            mcp.handle(message)
        payload = stdout.write.call_args.args[0]
        parsed = __import__("json").loads(payload)
        self.assertEqual(parsed["id"], 5)
        self.assertIn("capabilities", parsed["result"])


if __name__ == "__main__":
    unittest.main()
