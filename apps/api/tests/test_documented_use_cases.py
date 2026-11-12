import json
import re
from datetime import date
from pathlib import Path

from app.agent.conversation import ConversationContext
from app.agent.orchestration import AgentOrchestrator
from app.agent.routing import Domain, RuleChain
from app.agent.tools import ToolGate, ToolInvocationPolicy, build_tool_registry
from app.modules.identity.domain import Actor, UserRole

DOC = Path(__file__).parents[3] / "docs" / "use-cases" / "test-prompts.md"
PROMPT_PATTERN = re.compile(r"<!-- validated-prompt (\{.*?\}) -->")
ACTION_PATTERN = re.compile(r"<!-- validated-action (\{.*?\}) -->")
REFERENCE_DATE = date(2026, 11, 11)


def _metadata(pattern: re.Pattern[str], content: str) -> list[dict[str, str]]:
    return [json.loads(match) for match in pattern.findall(content)]


def test_documented_prompts_match_routing_planning_and_tool_policies():
    content = DOC.read_text()
    cases = _metadata(PROMPT_PATTERN, content)
    assert cases
    assert len({case["id"] for case in cases}) == len(cases)

    chain = RuleChain()
    policy = AgentOrchestrator(rules=chain).policy
    registry = build_tool_registry()
    tool_policy = ToolInvocationPolicy()

    for case in cases:
        assert case["prompt"] in content, case["id"]
        route = chain.classify(case["prompt"])
        assert route.domain == case["domain"], case["id"]
        assert route.action == case["action"], case["id"]
        assert route.topic == case["topic"], case["id"]

        plan = policy.plan(route, case["prompt"], ConversationContext(), REFERENCE_DATE)
        assert plan.kind == case["plan"], case["id"]
        if expected_tool := case.get("tool"):
            assert plan.first_step is not None, case["id"]
            assert plan.first_step.tool_name == expected_tool, case["id"]
            gate = tool_policy.evaluate(registry.get(expected_tool), None)
            assert gate == case["anonymous_gate"], case["id"]
        else:
            assert plan.first_step is None, case["id"]


def test_documented_catalog_covers_every_domain_and_registered_tool():
    content = DOC.read_text()
    prompts = _metadata(PROMPT_PATTERN, content)
    actions = _metadata(ACTION_PATTERN, content)

    assert {case["domain"] for case in prompts} == {domain.value for domain in Domain}

    registry = build_tool_registry()
    documented_tools = {
        case["tool"] for case in [*prompts, *actions] if case.get("tool")
    }
    assert documented_tools == {spec.name for spec in registry.specs()}


def test_documented_write_actions_require_authentication_and_confirmation():
    content = DOC.read_text()
    actions = _metadata(ACTION_PATTERN, content)
    registry = build_tool_registry()
    policy = ToolInvocationPolicy()
    actor = Actor(id="documented-patient", role=UserRole.PATIENT)

    assert len({case["id"] for case in actions}) == len(actions)
    for case in actions:
        spec = registry.get(case["tool"])
        assert policy.evaluate(spec, None) == case["anonymous_gate"], case["id"]
        assert policy.evaluate(spec, actor) == case["authenticated_gate"], case["id"]
        assert policy.evaluate(spec, actor, confirmed=True) == ToolGate.EXECUTE, case["id"]
