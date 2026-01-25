import unittest
from services.history_manager import history_manager

class TestHistoryManager(unittest.TestCase):
    def test_prompt_and_response(self):
        user_id = "test-user-1"
        history_manager.clear_history(user_id)
        history_manager.record_prompt(user_id, "Hello?")
        history_manager.record_response(user_id, "Hi there!")
        hist = history_manager.get_history(user_id)
        self.assertEqual(hist[0]["role"], "user")
        self.assertEqual(hist[0]["content"], "Hello?")
        self.assertEqual(hist[1]["role"], "assistant")
        self.assertEqual(hist[1]["content"], "Hi there!")

    def test_tool_recording(self):
        user_id = "test-user-2"
        history_manager.clear_history(user_id)
        history_manager.record_tool(user_id, "web_search", {"query": "python"})
        hist = history_manager.get_history(user_id)
        self.assertEqual(hist[0]["role"], "tool")
        self.assertEqual(hist[0]["tool_name"], "web_search")
        self.assertEqual(hist[0]["parameters"]["query"], "python")

    def test_event_log(self):
        user_id = "test-user-3"
        history_manager.clear_events()
        history_manager.record_event(user_id, "test", "something happened", {"foo": 1})
        events = history_manager.get_events()
        self.assertEqual(events[-1]["user_id"], user_id)
        self.assertEqual(events[-1]["kind"], "test")
        self.assertEqual(events[-1]["message"], "something happened")
        self.assertEqual(events[-1]["extra"]["foo"], 1)

    def test_history_limit(self):
        user_id = "test-user-4"
        history_manager.clear_history(user_id)
        for i in range(60):
            history_manager.record_prompt(user_id, f"msg {i}")
        hist = history_manager.get_history(user_id, limit=10)
        self.assertEqual(len(hist), 10)
        self.assertEqual(hist[-1]["content"], "msg 59")

if __name__ == "__main__":
    unittest.main()
