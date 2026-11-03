# backend/tests/test_checkin.py
import pytest
from unittest.mock import MagicMock, patch
from app.agents import checkin

@pytest.mark.asyncio
@patch("app.agents.checkin.Groq")
async def test_checkin_agent_barrier_detection(mock_groq_class, monkeypatch):
    # Provide a mock API key so checkin.py doesn't raise ValueError
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")

    # 1. Mock the Groq client and response for a barrier scenario
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client

    # Mock tool call object returned by Grok
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "report_barrier"
    mock_tool_call.function.arguments = '{"task_id": "task_104", "barrier_type": "cost"}'

    mock_message = MagicMock()
    mock_message.content = "I understand you are having trouble affording your refill."
    mock_message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_client.chat.completions.create.return_value = mock_response

    # 2. Define input payload
    payload = {
        "message": "I can't afford my medication refill this week.",
        "care_plan": {"tasks": [{"id": "task_104", "description": "Take Lisinopril"}]},
        "history": []
    }

    # 3. Execute agent run function
    result = await checkin.run(payload)

    # 4. Assertions matching Olamide's expected contract
    assert result["intent"] == "report_barrier"
    assert result["task_id"] == "task_104"
    assert result["barrier_type"] == "cost"
    assert result["requires_confirmation"] is True
    assert "affording" in result["reply_draft"]


@pytest.mark.asyncio
@patch("app.agents.checkin.Groq")
async def test_checkin_agent_task_done(mock_groq_class, monkeypatch):
    # Provide a mock API key so checkin.py doesn't raise ValueError
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")

    # 1. Mock the Groq client for a task completion scenario
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client

    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "mark_task_done"
    mock_tool_call.function.arguments = '{"task_id": "task_105"}'

    mock_message = MagicMock()
    mock_message.content = "Great job taking your morning medication!"
    mock_message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_client.chat.completions.create.return_value = mock_response

    payload = {
        "message": "I took my pills just now.",
        "care_plan": {"tasks": [{"id": "task_105", "description": "Metformin 500mg"}]},
        "history": []
    }

    result = await checkin.run(payload)

    assert result["intent"] == "mark_task_done"
    assert result["task_id"] == "task_105"
    assert result["barrier_type"] is None
    assert result["requires_confirmation"] is False
    assert "Great job" in result["reply_draft"]