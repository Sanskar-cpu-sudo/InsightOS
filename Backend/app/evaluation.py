"""
evaluation.py

This is the Evaluation Engine. After the Decision Agent produces an
answer, this file checks how GOOD that answer actually is.

We use RAGAS, a well known open source library for evaluating RAG
(retrieval + generation) systems. Instead of writing our own scoring
logic, RAGAS uses an LLM as a judge to check the answer properly.

We use two RAGAS metrics:

1. faithfulness
   Checks if the claims in the answer are actually supported by the
   evidence we gave it. Low score = the answer contains things that
   are not backed by the evidence (possible hallucination).

2. answer_relevancy
   Checks if the answer actually addresses the original question or
   anomaly, instead of drifting off topic.

RAGAS needs a judge LLM to do this checking. We use Groq, the same
provider we already use for the Decision Agent, and our own
sentence-transformers model for the embeddings RAGAS also needs.

We also record latency and cost, which were already calculated in
llm_gateway.py and passed along inside the decision result.
"""

import sys
import types

# WORKAROUND: ragas 0.4.3 tries to import a Google VertexAI integration
# (langchain_community.chat_models.vertexai) that no longer exists in
# newer versions of langchain-community. We don't use VertexAI at all
# (we use Groq), so we create a fake empty version of that module here.
# This must run BEFORE ragas is imported below, or the import will
# crash with "ModuleNotFoundError: No module named
# 'langchain_community.chat_models.vertexai'".
_fake_vertexai_module = types.ModuleType("langchain_community.chat_models.vertexai")


class _FakeChatVertexAI:
    pass


_fake_vertexai_module.ChatVertexAI = _FakeChatVertexAI
sys.modules["langchain_community.chat_models.vertexai"] = _fake_vertexai_module

from openai import OpenAI as OpenAICompatibleClient
from ragas.llms import llm_factory
from ragas.embeddings import BaseRagasEmbeddings
from ragas import evaluate, EvaluationDataset
from ragas.metrics import faithfulness, answer_relevancy

from app.config import get_settings
from app.vector_store import embed

settings = get_settings()


class SentenceTransformerEmbeddings(BaseRagasEmbeddings):
    """
    A small wrapper so RAGAS can use our own sentence-transformers model
    instead of needing an OpenAI embeddings key.

    RAGAS requires both sync AND async versions of embed_query/
    embed_documents. Our embedding model runs locally on your machine
    (not over the network), so there's no real "waiting" to do - the
    async versions just call the normal sync versions directly.
    """
    def embed_query(self, text):
        return embed([text])[0]

    def embed_documents(self, texts):
        return embed(texts)

    async def aembed_query(self, text):
        return self.embed_query(text)

    async def aembed_documents(self, texts):
        return self.embed_documents(texts)


def get_judge_llm():
    client = OpenAICompatibleClient(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    judge_llm = llm_factory(settings.LLM_MODEL, client=client)
    return judge_llm


def anomaly_to_statement(anomaly: dict) -> str:
    """
    Turns an anomaly dict from the Data Agent into a plain, declarative
    FACT sentence - not a question. This is meant to be used as the
    `original_topic` passed into evaluate_decision() for automatic
    (non-question) decisions, so faithfulness checking has something
    real to verify revenue/metric-related claims against.

    Example input:
        {"metric": "revenue", "percent_change": -38.4, "type": "point_anomaly"}
    Example output:
        "Business data: revenue changed by -38.4 percent compared to the recent average."
    """
    metric = anomaly.get("metric", "a business metric")
    change = anomaly.get("percent_change", anomaly.get("total_percent_change", "an unknown amount"))

    if anomaly.get("type") == "trend_anomaly":
        return f"Business data: {metric} has been declining, a total change of {change} percent over the recent period."
    return f"Business data: {metric} changed by {change} percent compared to the recent average."


def evaluate_decision(decision_result: dict, real_evidence: list, original_topic: str) -> dict:
    """
    Main function other code calls to use the Evaluation Engine.

    decision_result: the dict returned by run_decision_agent()
    real_evidence: the evidence list from the Knowledge Agent
    original_topic: a plain text DECLARATIVE FACT describing the
                     anomaly or question - NOT a bare question like
                     "why is revenue dropping". For anomaly-based
                     decisions, build this with anomaly_to_statement()
                     first. For user questions, the question text itself
                     is fine for the relevance check, but won't help
                     faithfulness verify any numeric claims - that is
                     a known, expected limitation for on-demand questions.

    Returns a dict with faithfulness_score, relevance_score, latency
    and token usage.
    """
    if not decision_result.get("success"):
        # nothing to evaluate if the decision agent itself failed
        return {
            "faithfulness_score": 0.0,
            "relevance_score": 0.0,
            "latency_seconds": None,
            "input_tokens": None,
            "output_tokens": None,
        }

    answer_text = decision_result.get("root_cause", "")

    # We include a description of the anomaly/topic as extra context,
    # alongside the evidence texts. Why: the Decision Agent's answer
    # often connects the evidence (e.g. "customers report slowness") to
    # numbers from the anomaly itself (e.g. "revenue dropped 30%") - if
    # we only give RAGAS the evidence texts, any mention of "revenue"
    # in the answer looks unsupported, even though it's genuinely
    # grounded in the anomaly data the Decision Agent was given.
    #
    # IMPORTANT: this extra context must be a DECLARATIVE FACT, not a
    # question. A faithfulness checker verifies claims against stated
    # facts - a question like "why is revenue dropping" asserts nothing,
    # so it can't support any claim. "Anomaly data: why is revenue
    # dropping" does NOT work. Something like "Revenue dropped by 30
    # percent compared to the 30-day average" DOES work, because it's
    # an actual statement the claim can be checked against.
    context_texts = [item["text"] for item in real_evidence] if real_evidence else []
    context_texts.append(original_topic)

    # RAGAS expects a dataset with one row per answer we want to check.
    # NOTE: this version of ragas uses these exact column names -
    # user_input (the question), response (the answer), and
    # retrieved_contexts (the evidence) - not "question"/"answer"/
    # "contexts" like older versions/tutorials use.
    row = {
        "user_input": original_topic,
        "response": answer_text,
        "retrieved_contexts": context_texts,
    }
    dataset = EvaluationDataset.from_list([row])

    scores = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=get_judge_llm(),
        embeddings=SentenceTransformerEmbeddings(),
    )

    scores_df = scores.to_pandas()
    faithfulness_score = float(scores_df["faithfulness"][0])
    relevance_score = float(scores_df["answer_relevancy"][0])

    llm_info = decision_result.get("llm_info", {})

    return {
        "faithfulness_score": round(faithfulness_score, 3),
        "relevance_score": round(relevance_score, 3),
        "latency_seconds": llm_info.get("latency_seconds"),
        "input_tokens": llm_info.get("input_tokens"),
        "output_tokens": llm_info.get("output_tokens"),
    }