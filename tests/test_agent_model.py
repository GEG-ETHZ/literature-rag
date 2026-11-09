import importlib

import pytest
from google.adk.models import Gemini


@pytest.fixture
def load_agent(monkeypatch):
    """Import agent.agent fresh under the given environment, ignoring any local .env."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("vertexai.init", lambda **_kwargs: None)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("RAG_CORPUS", "projects/1/locations/europe-west1/ragCorpora/2")

    def _load(**env):
        # agent.py writes these with os.environ directly; registering them here restores them.
        for key in (
            "AGENT_MODEL_NAME",
            "AGENT_MODEL_LOCATION",
            "GOOGLE_CLOUD_LOCATION",
            "GOOGLE_GENAI_USE_VERTEXAI",
        ):
            monkeypatch.setenv(key, "")
            monkeypatch.delenv(key)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        import agent.agent

        return importlib.reload(agent.agent)

    return _load


def test_model_runs_on_the_eu_endpoint_by_default(load_agent):
    module = load_agent()

    model = module.root_agent.model
    assert isinstance(model, Gemini)
    assert model.model == "gemini-3.8-flash"
    assert model.client_kwargs == {"location": "eu"}


def test_model_name_and_location_come_from_the_environment(load_agent):
    module = load_agent(AGENT_MODEL_NAME="gemini-3.5-flash", AGENT_MODEL_LOCATION="europe-west3")

    assert module.root_agent.model.model == "gemini-3.5-flash"
    assert module.root_agent.model.client_kwargs == {"location": "europe-west3"}


def test_retrieval_stays_in_the_corpus_region(load_agent):
    load_agent()

    import os

    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "europe-west1"
