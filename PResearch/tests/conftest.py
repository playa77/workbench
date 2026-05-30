"""Shared test fixtures."""

import pytest

from presearch.config import PResearchConfig
from presearch.models.mind_map import MindMap, Source
from presearch.models.state import ResearchState


@pytest.fixture
def config():
    return PResearchConfig(custom_api_key="test-key", brave_api_key="test-brave-key")


@pytest.fixture
def mind_map():
    return MindMap.create("test query")


@pytest.fixture
def state():
    return ResearchState.create("test query", max_iterations=5)


@pytest.fixture
def sample_source():
    return Source(url="https://example.com", title="Example")
