import pytest
from services.history_manager import history_manager

def test_prompt_and_response():
    user_id = "test-user-1"
    history_manager.clear_history(user_id)
    history_manager.record_prompt(user_id, "Hello?")
    history_manager.record_response(user_id, "Hi there!")
    hist = history_manager.get_history(user_id)
    assert hist[0]["role"] == "user"
    assert hist[0]["content"] == "Hello?"
    assert hist[1]["role"] == "assistant"
    assert hist[1]["content"] == "Hi there!"

def test_tool_recording():
    user_id = "test-user-2"
    history_manager.clear_history(user_id)
    history_manager.record_tool(user_id, "web_search", {"query": "python"})
    hist = history_manager.get_history(user_id)
    assert hist[0]["role"] == "tool"
    assert hist[0]["tool_name"] == "web_search"
    assert hist[0]["parameters"]["query"] == "python"

def test_event_log():
    user_id = "test-user-3"
    history_manager.clear_events()
    history_manager.record_event(user_id, "test", "something happened", {"foo": 1})
    events = history_manager.get_events()
    assert events[-1]["user_id"] == user_id
    assert events[-1]["kind"] == "test"
    assert events[-1]["message"] == "something happened"
    assert events[-1]["extra"]["foo"] == 1

def test_history_limit():
    user_id = "test-user-4"
    history_manager.clear_history(user_id)
    for i in range(60):
        history_manager.record_prompt(user_id, f"msg {i}")
    hist = history_manager.get_history(user_id, limit=10)
    assert len(hist) == 10
    assert hist[-1]["content"] == "msg 59"
