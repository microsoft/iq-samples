# Copyright (c) Microsoft. All rights reserved.

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv
from pytest_agent_evals import (
    EvaluatorResults,
    evals,
    AzureOpenAIModelConfig,
    FoundryAgentConfig,
    BuiltInEvaluatorConfig,
    CustomCodeEvaluatorConfig,
)
from evaluators import policy_completeness_grader
from tracing_setup import setup_foundry_tracing

load_dotenv(dotenv_path=_HERE / ".env")
os.chdir(_HERE)
setup_foundry_tracing("travel-agent-evals")

EVAL_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
EVAL_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")


@evals.dataset("data.jsonl")
@evals.judge_model(AzureOpenAIModelConfig(deployment_name=EVAL_DEPLOYMENT, endpoint=EVAL_ENDPOINT))
@evals.agent(FoundryAgentConfig(agent_name="TravelAgent", project_endpoint=PROJECT_ENDPOINT))
class Test_TravelAgent:
    """Evaluation suite for the hosted TravelAgent (Foundry IQ + Work IQ Mail).

    A fully grounded agent should PASS all evaluators — it retrieves real
    policy data from the knowledge base AND checks email for temporary
    overrides via Work IQ Mail.
    """

    @evals.evaluator(BuiltInEvaluatorConfig(name="intent_resolution"))
    def test_intent_resolution(self, evaluator_results: EvaluatorResults):
        assert evaluator_results.intent_resolution.result == "pass"

    @evals.evaluator(CustomCodeEvaluatorConfig(
        name="policy_completeness",
        grader=policy_completeness_grader,
        threshold=0.4,
    ))
    def test_policy_completeness(self, evaluator_results: EvaluatorResults):
        assert evaluator_results.policy_completeness.result == "pass"

    @evals.evaluator(CustomCodeEvaluatorConfig(
        name="email_awareness",
        grader=policy_completeness_grader,
        threshold=0.6,
    ))
    def test_email_awareness(self, evaluator_results: EvaluatorResults):
        assert evaluator_results.email_awareness.result == "pass"
