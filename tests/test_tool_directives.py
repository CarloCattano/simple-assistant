import unittest

import utils.tool_directives as td
from utils.tool_directives import ToolDirectiveError


class ToolDirectivesTests(unittest.TestCase):
    def setUp(self) -> None:
        # Save originals so we can restore after patching.
        self._orig_resolve = td.resolve_tool_identifier
        self._orig_translate_cmd = td.translate_instruction_to_command
        self._orig_translate_query = td.translate_instruction_to_query

    def tearDown(self) -> None:
        td.resolve_tool_identifier = self._orig_resolve
        td.translate_instruction_to_command = self._orig_translate_cmd
        td.translate_instruction_to_query = self._orig_translate_query

    def test_normalize_tool_parameters_web_search_translates_query(self):
        calls = {}

        def fake_translate(q: str) -> str:
            calls["arg"] = q
            return "normalized query"

        td.translate_instruction_to_query = fake_translate

        params = {"query": "  original query  "}
        normalized = td._normalize_tool_parameters("web_search", params)

        self.assertEqual(normalized["query"], "normalized query")
        self.assertEqual(calls["arg"], "original query")

    def test_extract_tool_request_json_payload(self):
        td.translate_instruction_to_query = lambda q: f"q:{q}"

        text = "/web {\"name\": \"web_search\", \"parameters\": {\"query\": \"foo\"}}"
        result = td.extract_tool_request(text)
        self.assertIsNotNone(result, "extract_tool_request returned None")
        name, params = result
        self.assertEqual(name, "web_search")
        self.assertEqual(params["query"], "q:foo")

    def test_parse_run_tool_missing_args_raises(self):
        def fake_resolve(identifier: str):
            return "shell_agent", {"parameters": {"prompt": {"type": "string"}}}

        td.resolve_tool_identifier = fake_resolve

        with self.assertRaises(ToolDirectiveError):
            td._parse_tool_directive("run tool agent")

    def test_derive_followup_tool_request_builds_query(self):
        td.translate_instruction_to_query = lambda text: "refined query"

        tool_metadata = {"tool_name": "web_search", "parameters": {"query": "linux commands"}}

        result = td.derive_followup_tool_request(
            "now include windows commands",
            "original prompt",
            tool_metadata,
        )

        tool_name, params, display = result
        self.assertEqual(tool_name, "web_search")
        self.assertEqual(params["query"], "refined query")
        self.assertEqual(display, "refined query")


if __name__ == "__main__":
    unittest.main()
