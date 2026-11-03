# backend/tests/test_checkin.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents import checkin


def mock_groq(mock_groq_class, content, tool_name=None, arguments=None):
    """Make AsyncGroq return one reply, with an optional tool call."""
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client

    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = None
    if tool_name:
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = tool_name
        mock_tool_call.function.arguments = arguments
        mock_message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture(autouse=True)
def groq_key(monkeypatch):
    # Provide a mock API key so checkin.py doesn't raise ValueError
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")


@pytest.mark.asyncio
@patch("app.agents.checkin.AsyncGroq")
async def test_checkin_agent_barrier_detection(mock_groq_class):
    mock_groq(mock_groq_class, "I understand you are having trouble affording your refill.",
              "report_barrier", '{"task_id": "task_104", "barrier_type": "cost"}')

    payload = {
        "message": "I can't afford my medication refill this week.",
        "care_plan": {"tasks": [{"id": "task_104", "description": "Take Lisinopril"}]},
        "history": []
    }

    result = await checkin.run(payload)

    # Assertions matching Olamide's expected contract
    assert result["intent"] == "report_barrier"
    assert result["task_id"] == "task_104"
    assert result["barrier_type"] == "cost"
    assert result["requires_confirmation"] is True
    assert result["confidence_state"] == "confident"
    assert "affording" in result["reply_draft"]


@pytest.mark.asyncio
@patch("app.agents.checkin.AsyncGroq")
async def test_checkin_agent_task_done(mock_groq_class):
    mock_groq(mock_groq_class, "Great job taking your morning medication!",
              "mark_task_done", '{"task_id": "task_105"}')

    payload = {
        "message": "I took my pills just now.",
        "care_plan": {"tasks": [{"id": "task_105", "description": "Metformin 500mg"}]},
        "history": []
    }

    result = await checkin.run(payload)

    assert result["intent"] == "mark_task_done"
    assert result["task_id"] == "task_105"
    assert result["barrier_type"] is None
    # Marking a task done changes the record, so the patient confirms first
    assert result["requires_confirmation"] is True
    assert "Great job" in result["reply_draft"]


@pytest.mark.asyncio
@patch("app.agents.checkin.AsyncGroq")
async def test_checkin_agent_rejects_unknown_task(mock_groq_class):
    mock_groq(mock_groq_class, None, "mark_task_done", '{"task_id": "task_999"}')

    payload = {
        "message": "Done with it.",
        "care_plan": {"tasks": [{"id": "task_105", "description": "Metformin 500mg"}]},
        "history": []
    }

    result = await checkin.run(payload)

    assert result["intent"] == "general_checkin"
    assert result["task_id"] is None
    assert result["requires_confirmation"] is False
    assert result["confidence_state"] == "needs_confirmation"
    assert result["reply_draft"]


@pytest.mark.asyncio
@patch("app.agents.checkin.AsyncGroq")
async def test_checkin_agent_rejects_unknown_barrier(mock_groq_class):
    mock_groq(mock_groq_class, "Thanks for telling me.",
              "report_barrier", '{"task_id": "task_104", "barrier_type": "stock_out"}')

    payload = {
        "message": "The pharmacy has none left.",
        "care_plan": {"tasks": [{"id": "task_104", "description": "Take Lisinopril"}]},
        "history": []
    }

    result = await checkin.run(payload)

    assert result["intent"] == "general_checkin"
    assert result["barrier_type"] is None
    assert result["confidence_state"] == "needs_confirmation"


@pytest.mark.asyncio
@patch("app.agents.checkin.AsyncGroq")
async def test_checkin_agent_plain_reply(mock_groq_class):
    mock_groq(mock_groq_class, "Which medicine do you mean?")

    result = await checkin.run({"message": "I took it", "care_plan": {"tasks": []}, "history": []})

    assert result["intent"] == "general_checkin"
    assert result["confidence_state"] == "confident"
    assert result["reply_draft"] == "Which medicine do you mean?"
