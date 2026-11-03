# backend/tests/test_language.py
# Language & Literacy Agent: a translation is kept only if numbers and protected terms survive.
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import language
from tests.test_chat import say, tola

SOURCE = "Your medicine Amlodipine 5 mg tablet, 1 tablet, is due at 09:00."


async def translate(model_text, **payload):
    with patch("app.agents.language.ask_groq_json", AsyncMock(return_value={"text": model_text, "unsure": []})) as mock:
        result = await language.run({"text": SOURCE, "language": "Yoruba", "reading_level": "basic",
                                     "protected_terms": ["Amlodipine 5 mg tablet"], **payload})
    return result, mock


@pytest.mark.asyncio
async def test_good_translation_is_used():
    result, _ = await translate("Oogun rẹ Amlodipine 5 mg tablet, 1 tablet, yẹ ni 09:00.")
    assert result["adapted"] and result["language"] == "Yoruba" and result["english"] == SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize("model_text, problem", [
    ("Oogun rẹ Amlodipine 5 mg tablet, 2 tablet, yẹ ni 09:00.", "number"),       # dose changed
    ("Oogun rẹ Amlodipine 5 mg tablet, 1 tablet.", "number"),                    # time dropped
    ("Oogun rẹ, 5 mg, 1 tablet, yẹ ni 09:00.", "Amlodipine"),                    # medicine name lost
])
async def test_translation_that_changes_numbers_or_names_falls_back_to_english(model_text, problem):
    result, _ = await translate(model_text)
    assert not result["adapted"] and result["text"] == SOURCE
    assert any(problem in flag for flag in result["uncertainty_flags"])


@pytest.mark.asyncio
async def test_plain_english_is_not_sent_to_the_model():
    result, mock = await translate("unused", language="English", reading_level="standard")
    mock.assert_not_awaited()
    assert result["text"] == SOURCE


def test_chat_reply_in_the_patients_language_keeps_the_english(client, mailbox):
    tola(client, mailbox)
    with patch("app.agents.language.ask_groq_json", AsyncMock(return_value={"text": "O ṣeun. Mo ti kọ ọ silẹ.", "unsure": []})):
        reply = say(client, "Done", quick_reply="done")["reply"]
    assert reply["original_text"] == "O ṣeun. Mo ti kọ ọ silẹ." and reply["english_text"] == "Thank you. I have noted that you took it."
    assert reply["language"] == "Yoruba" and reply["number_check_passed"] is True


def test_emergency_line_uses_the_prepared_translation_not_the_model(client, mailbox):
    tola(client, mailbox)
    agent = AsyncMock()
    with patch("app.agents.language.ask_groq_json", agent):
        reply = say(client, "My chest hurts")["reply"]
    agent.assert_not_awaited()
    assert reply["original_text"].startswith("Tí ara yín kò bá yá rárá") and reply["original_text"].endswith("I have sent this to your care team.")
