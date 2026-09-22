import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_agent_policy_eval import is_allowed  # noqa: E402


class AgentPolicyEvaluationTest(unittest.TestCase):
    def test_policy_fixtures_match_server_contracts(self):
        data = json.loads(
            (HERE / "datasets/synthetic-agent-policy-v1.json").read_text(encoding="utf-8")
        )
        mismatches = [
            case["case_id"]
            for case in data["cases"]
            if is_allowed(case) != case["expected_allowed"]
        ]
        self.assertEqual(mismatches, [])

    def test_untrusted_arbitrary_tools_are_rejected(self):
        for tool in ("fetch_url", "execute_sql", "run_shell"):
            self.assertFalse(is_allowed({"tool": tool, "arguments": {}}))
