"""Tests for the refactored agent.py module.

Validates that:
- AgentDeps uses asyncpg.Pool, VertexEmbeddingClient, and slack_user_id
- No OpenAI or Supabase imports remain
- Agent is initialized with vertex_provider.get_model()
- Tool wrappers pass the correct dependency types
"""

import ast
import dataclasses
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.models.test import TestModel


def _create_mock_tools_module():
    """Create a fake 'tools' module with stub functions so agent.py can import
    without pulling in RestrictedPython / supabase / openai from tools.py."""
    mod = types.ModuleType("tools")
    for name in (
        "web_search_tool",
        "image_analysis_tool",
        "retrieve_relevant_documents_tool",
        "list_documents_tool",
        "get_document_content_tool",
        "execute_sql_query_tool",
        "execute_safe_code_tool",
    ):
        setattr(mod, name, MagicMock())
    return mod


def _create_mock_prompt_module():
    """Create a fake 'prompt' module with the system prompt constant."""
    mod = types.ModuleType("prompt")
    mod.AGENT_SYSTEM_PROMPT = "You are a test agent."
    return mod


@pytest.fixture(autouse=True)
def _isolate_agent_imports():
    """Inject mock modules for tools/prompt before each test,
    then clean up sys.modules afterwards to avoid cross-test pollution."""
    saved = {}
    for mod_name in ("tools", "prompt", "agent"):
        saved[mod_name] = sys.modules.pop(mod_name, None)

    sys.modules["tools"] = _create_mock_tools_module()
    sys.modules["prompt"] = _create_mock_prompt_module()

    yield

    for mod_name, original in saved.items():
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original


def _import_agent():
    """Import agent.py with vertex_provider.get_model() returning a TestModel."""
    test_model = TestModel()
    with patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
        "LLM_CHOICE": "gemini-2.0-flash",
    }):
        with patch("vertex_provider.get_model", return_value=test_model):
            sys.modules.pop("agent", None)
            import agent as agent_mod
    return agent_mod


# ---- AgentDeps dataclass tests ----

class TestAgentDepsDataclass:
    """Verify AgentDeps has the correct fields after refactor."""

    @pytest.fixture(autouse=True)
    def load_agent(self):
        self.AgentDeps = _import_agent().AgentDeps

    def test_has_db_pool_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "db_pool" in fields

    def test_has_embedding_client_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "embedding_client" in fields

    def test_has_slack_user_id_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "slack_user_id" in fields

    def test_no_supabase_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "supabase" not in fields

    def test_has_http_client_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "http_client" in fields

    def test_has_memories_field(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        assert "memories" in fields

    def test_all_expected_fields_present(self):
        fields = {f.name for f in dataclasses.fields(self.AgentDeps)}
        expected = {
            "db_pool", "embedding_client", "http_client",
            "brave_api_key", "searxng_base_url", "memories", "slack_user_id",
        }
        assert fields == expected


# ---- AST-based import verification (no runtime import needed) ----

class TestNoLegacyImports:
    """Verify agent.py has no OpenAI or Supabase imports via AST inspection."""

    @pytest.fixture(autouse=True)
    def parse_agent_source(self):
        agent_path = os.path.join(
            os.path.dirname(__file__), os.pardir, "agent.py"
        )
        with open(agent_path) as f:
            self.source = f.read()
        self.tree = ast.parse(self.source)

    def _get_all_imported_names(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
                for alias in node.names:
                    names.add(alias.name)
        return names

    def test_no_openai_imports(self):
        names = self._get_all_imported_names()
        openai_names = {n for n in names if "openai" in n.lower()}
        assert openai_names == set(), f"Found OpenAI imports: {openai_names}"

    def test_no_supabase_imports(self):
        names = self._get_all_imported_names()
        supabase_names = {n for n in names if "supabase" in n.lower()}
        assert supabase_names == set(), f"Found Supabase imports: {supabase_names}"

    def test_no_mcp_server_http_import(self):
        names = self._get_all_imported_names()
        assert "MCPServerHTTP" not in names

    def test_imports_vertex_provider(self):
        names = self._get_all_imported_names()
        assert "vertex_provider" in names or "get_model" in names

    def test_imports_vertex_embeddings(self):
        names = self._get_all_imported_names()
        assert "VertexEmbeddingClient" in names

    def test_imports_asyncpg(self):
        names = self._get_all_imported_names()
        assert "asyncpg" in names

    def test_no_local_get_model_function(self):
        """No locally defined get_model() — should come from vertex_provider."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_model":
                pytest.fail(
                    "Found local get_model() — should use vertex_provider.get_model()"
                )


# ---- Agent initialization tests ----

class TestAgentInitialization:
    """Verify the agent is created with vertex_provider.get_model()."""

    def test_agent_uses_vertex_model(self):
        test_model = TestModel()
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_REGION": "us-central1",
            "LLM_CHOICE": "gemini-2.0-flash",
        }):
            with patch(
                "vertex_provider.get_model", return_value=test_model
            ) as mock_get:
                sys.modules.pop("agent", None)
                import agent as agent_mod
                mock_get.assert_called_once()

    def test_agent_has_expected_tools_registered(self):
        agent_mod = _import_agent()
        toolset = agent_mod.agent._function_toolset
        tool_names = {t.name for t in toolset.tools.values()}
        expected_tools = {
            "web_search",
            "retrieve_relevant_documents",
            "list_documents",
            "get_document_content",
            "execute_sql_query",
            "image_analysis",
            "execute_code",
        }
        assert expected_tools.issubset(tool_names), (
            f"Missing tools: {expected_tools - tool_names}"
        )
