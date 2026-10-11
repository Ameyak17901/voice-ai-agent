"""
Automated unit and regression test suite for:
- ResilientChatGPTAgent get_chat_parameters Google Gemini OpenAI tools translation
- openai_get_tokens chunk streaming parser supporting modern delta.tool_calls
- End-to-end agent initialization with tool schemas for persona 'receptionist'
"""
import pytest
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.transcript import Transcript
from vocode.streaming.agent.openai_utils import openai_get_tokens
from vocode.streaming.models.actions import FunctionFragment
from backend.agent_factory import ResilientChatGPTAgent, create_agent
from backend.actions.appointment_actions import (
    CheckAvailabilityActionConfig,
    BookAppointmentActionConfig,
    GetCompanyInfoActionConfig,
)
from backend.actions.factory import CustomActionFactory


# Dummy Chunk Classes replicating OpenAI / Google Gemini streaming output
class DummyChoiceDeltaFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class DummyChoiceDeltaToolCall:
    def __init__(self, name, arguments):
        self.function = DummyChoiceDeltaFunction(name=name, arguments=arguments)


class DummyDelta:
    def __init__(self, content=None, tool_calls=None, function_call=None):
        self.content = content
        self.tool_calls = tool_calls
        self.function_call = function_call


class DummyChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class DummyChunk:
    def __init__(self, choices):
        self.choices = choices


def test_gemini_parameter_translation():
    """Verify ResilientChatGPTAgent converts legacy 'functions' to modern 'tools'."""
    actions = [
        CheckAvailabilityActionConfig(),
        BookAppointmentActionConfig(),
        GetCompanyInfoActionConfig(),
    ]
    action_factory = CustomActionFactory(actions=actions)

    gemini_config = ChatGPTAgentConfig(
        initial_message=BaseMessage(text="Hello"),
        prompt_preamble="You are an assistant.",
        model_name="gemini-1.5-flash",
        openai_api_key="dummy_gemini_key",
        base_url_override="https://generativelanguage.googleapis.com/v1beta/openai/",
        actions=actions,
    )
    agent = ResilientChatGPTAgent(gemini_config, action_factory=action_factory)

    transcript = Transcript()
    transcript.add_human_message(text="Can you check availability?", conversation_id="test_conv")
    agent.attach_transcript(transcript)

    params = agent.get_chat_parameters()

    assert "functions" not in params, "Legacy 'functions' parameter MUST be absent for Gemini endpoint"
    assert "tools" in params, "Modern 'tools' parameter MUST be present"
    assert len(params["tools"]) == 3

    for tool in params["tools"]:
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "parameters" in tool["function"]

    tool_names = [t["function"]["name"] for t in params["tools"]]
    assert "check_availability" in tool_names
    assert "book_appointment" in tool_names
    assert "get_company_info" in tool_names


@pytest.mark.asyncio
async def test_openai_get_tokens_streaming_tool_calls():
    """Verify openai_get_tokens correctly parses streaming delta.tool_calls chunks into FunctionFragments."""
    async def synthetic_gemini_stream():
        # 1. Text fragment
        yield DummyChunk([DummyChoice(DummyDelta(content="Checking for you..."))])
        # 2. Modern tool_call initiation fragment
        yield DummyChunk([DummyChoice(DummyDelta(tool_calls=[
            DummyChoiceDeltaToolCall(name="check_availability", arguments="")
        ]))])
        # 3. Modern tool_call arguments delta fragment
        yield DummyChunk([DummyChoice(DummyDelta(tool_calls=[
            DummyChoiceDeltaToolCall(name="", arguments='{"date": "today"}')
        ]))])
        # 4. Stream completion chunk
        yield DummyChunk([DummyChoice(DummyDelta(), finish_reason="stop")])

    tokens = []
    async for token in openai_get_tokens(synthetic_gemini_stream()):
        tokens.append(token)

    assert len(tokens) == 3
    assert tokens[0] == "Checking for you..."
    assert isinstance(tokens[1], FunctionFragment)
    assert tokens[1].name == "check_availability"
    assert isinstance(tokens[2], FunctionFragment)
    assert tokens[2].arguments == '{"date": "today"}'


def test_agent_factory_creation_with_tools():
    """Verify end-to-end agent factory creates resilient agent configured with tool schemas."""
    user_settings = {
        "gemini_api_key": "dummy_test_gemini_key",
        "default_persona": "receptionist",
    }
    agent = create_agent(persona_key="receptionist", user_id=1, user_settings=user_settings)
    assert isinstance(agent, ResilientChatGPTAgent)
    assert agent.fallback_agent.persona == "receptionist"

    transcript = Transcript()
    transcript.add_human_message(text="What times are available?", conversation_id="test_conv_factory")
    agent.attach_transcript(transcript)

    params = agent.get_chat_parameters()
    assert "functions" not in params
    assert "tools" in params
