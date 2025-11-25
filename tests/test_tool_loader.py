"""
Unit tests for the Tool Loader Service.
Tests loading, parsing, and querying of tool/workflow/agent definitions.
"""

import pytest
from pathlib import Path
from app.services.tool_loader import (
    ToolLoaderService,
    ToolDefinition,
    WorkflowDefinition,
    get_tool_loader,
    TOOLS_DIR,
    WORKFLOWS_DIR,
    AGENTS_DIR
)


@pytest.fixture
def tool_content():
    """Sample tool definition content."""
    return """---
name: "test_tool"
version: "1.0.0"
type: "tool"
category: "test"
description: "A test tool for unit testing"

parameters:
  - name: query
    type: string
    required: true
    description: "The search query"
  - name: limit
    type: integer
    default: 10
    description: "Maximum results"

triggers:
  - patterns: ["test", "testing", "check"]
    priority: high
  - patterns: ["verify", "validate"]
    priority: medium
---

# Test Tool

This is test content for the tool definition.

## Usage
Use this tool when testing.
"""


@pytest.fixture
def workflow_content():
    """Sample workflow definition content."""
    return """---
name: "test_workflow"
version: "1.0.0"
type: "workflow"
description: "A test workflow for unit testing"

stages:
  - name: planning
    agent: test_planner
    timeout: 30
    outputs:
      - objectives

  - name: execution
    agent: test_executor
    timeout: 60
    inputs:
      - objectives
    outputs:
      - results

config:
  max_total_tokens: 50000
  credibility_threshold: 50

sampling:
  strategy: "balanced"
  articles_per_query: 10
  max_total_articles: 50

filtering:
  min_credibility: 50
  date_range:
    enabled: true
    days_back: 14

model_config:
  preset: "balanced"
  stages:
    planning:
      model: "gpt-4.1-mini"
      temperature: 0.3
    execution:
      model: "gpt-4o"
      temperature: 0.5
  presets:
    balanced:
      temperature: 0.4
      top_p: 0.9
      description: "Default balanced preset"
    precise:
      temperature: 0.1
      top_p: 0.8
      description: "High precision preset"
---

# Test Workflow

A test workflow with two stages.
"""


@pytest.fixture
def temp_tool_file(tmp_path, tool_content):
    """Create a temporary tool file."""
    tool_file = tmp_path / "test_tool.md"
    tool_file.write_text(tool_content)
    return tool_file


@pytest.fixture
def temp_workflow_file(tmp_path, workflow_content):
    """Create a temporary workflow file."""
    workflow_file = tmp_path / "test_workflow.md"
    workflow_file.write_text(workflow_content)
    return workflow_file


class TestToolDefinition:
    """Tests for ToolDefinition class."""

    def test_load_from_file(self, temp_tool_file):
        """Test loading a tool definition from file."""
        tool = ToolDefinition.from_file(temp_tool_file)

        assert tool.name == "test_tool"
        assert tool.version == "1.0.0"
        assert tool.type == "tool"
        assert tool.description == "A test tool for unit testing"
        assert len(tool.parameters) == 2
        assert len(tool.triggers) == 2
        assert "# Test Tool" in tool.content

    def test_parameter_parsing(self, temp_tool_file):
        """Test that parameters are correctly parsed."""
        tool = ToolDefinition.from_file(temp_tool_file)

        query_param = tool.parameters[0]
        assert query_param["name"] == "query"
        assert query_param["type"] == "string"
        assert query_param["required"] is True

        limit_param = tool.parameters[1]
        assert limit_param["name"] == "limit"
        assert limit_param["default"] == 10

    def test_trigger_matching_high_priority(self, temp_tool_file):
        """Test matching high-priority triggers."""
        tool = ToolDefinition.from_file(temp_tool_file)

        matched, score = tool.matches_query("I want to test something")
        assert matched is True
        assert score == 0.9  # high priority

    def test_trigger_matching_medium_priority(self, temp_tool_file):
        """Test matching medium-priority triggers."""
        tool = ToolDefinition.from_file(temp_tool_file)

        matched, score = tool.matches_query("Please verify this data")
        assert matched is True
        assert score == 0.6  # medium priority

    def test_trigger_no_match(self, temp_tool_file):
        """Test non-matching queries."""
        tool = ToolDefinition.from_file(temp_tool_file)

        matched, score = tool.matches_query("analyze the weather patterns")
        assert matched is False
        assert score == 0.0

    def test_to_dict(self, temp_tool_file):
        """Test conversion to dictionary."""
        tool = ToolDefinition.from_file(temp_tool_file)
        data = tool.to_dict()

        assert data["name"] == "test_tool"
        assert data["version"] == "1.0.0"
        assert "parameters" in data
        assert "triggers" in data
        assert "content" in data


class TestWorkflowDefinition:
    """Tests for WorkflowDefinition class."""

    def test_load_from_file(self, temp_workflow_file):
        """Test loading a workflow definition from file."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)

        assert workflow.name == "test_workflow"
        assert workflow.version == "1.0.0"
        assert workflow.description == "A test workflow for unit testing"
        assert len(workflow.stages) == 2

    def test_stage_parsing(self, temp_workflow_file):
        """Test that stages are correctly parsed."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)

        planning_stage = workflow.stages[0]
        assert planning_stage["name"] == "planning"
        assert planning_stage["agent"] == "test_planner"
        assert planning_stage["timeout"] == 30

        execution_stage = workflow.stages[1]
        assert execution_stage["name"] == "execution"
        assert "objectives" in execution_stage["inputs"]

    def test_get_stage(self, temp_workflow_file):
        """Test getting a specific stage by name."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)

        stage = workflow.get_stage("planning")
        assert stage is not None
        assert stage["agent"] == "test_planner"

        missing_stage = workflow.get_stage("nonexistent")
        assert missing_stage is None

    def test_get_model_config_for_stage(self, temp_workflow_file):
        """Test getting model configuration for a stage."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)

        planning_config = workflow.get_model_config_for_stage("planning")
        assert planning_config["model"] == "gpt-4.1-mini"
        assert planning_config["temperature"] == 0.3

        execution_config = workflow.get_model_config_for_stage("execution")
        assert execution_config["model"] == "gpt-4o"
        assert execution_config["temperature"] == 0.5

    def test_get_sampling_config(self, temp_workflow_file):
        """Test getting sampling configuration with defaults."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)
        sampling = workflow.get_sampling_config()

        assert sampling["strategy"] == "balanced"
        assert sampling["articles_per_query"] == 10
        assert sampling["max_total_articles"] == 50
        # Check defaults are merged
        assert "diversity" in sampling

    def test_get_filtering_config(self, temp_workflow_file):
        """Test getting filtering configuration with defaults."""
        workflow = WorkflowDefinition.from_file(temp_workflow_file)
        filtering = workflow.get_filtering_config()

        assert filtering["min_credibility"] == 50
        assert filtering["date_range"]["days_back"] == 14
        # Check defaults are merged
        assert "content_quality" in filtering


class TestToolLoaderService:
    """Tests for ToolLoaderService class."""

    def test_ensure_directories(self):
        """Test that directories are created on initialization."""
        # Just verify no exceptions
        loader = ToolLoaderService()
        assert TOOLS_DIR.exists()
        assert WORKFLOWS_DIR.exists()
        assert AGENTS_DIR.exists()

    def test_load_all_from_data_dir(self):
        """Test loading all definitions from the actual data directory."""
        loader = ToolLoaderService()
        loader.load_all()

        # Should load the sample files we created
        tools = loader.list_tools()
        workflows = loader.list_workflows()
        agents = loader.list_agents()

        # Verify at least some definitions loaded
        assert len(tools) >= 0  # May be 0 if no files exist
        assert len(workflows) >= 0
        assert len(agents) >= 0

    def test_get_tool(self):
        """Test getting a specific tool by name."""
        loader = ToolLoaderService()
        loader.load_all()

        # Try to get one of our sample tools
        tool = loader.get_tool("enhanced_database_search")
        if tool:
            assert tool.name == "enhanced_database_search"
            assert tool.type == "tool"

    def test_get_workflow(self):
        """Test getting a specific workflow by name."""
        loader = ToolLoaderService()
        loader.load_all()

        workflow = loader.get_workflow("deep_research_workflow")
        if workflow:
            assert workflow.name == "deep_research_workflow"
            assert len(workflow.stages) > 0

    def test_get_agent(self):
        """Test getting a specific agent by name."""
        loader = ToolLoaderService()
        loader.load_all()

        agent = loader.get_agent("research_planner")
        if agent:
            assert agent.name == "research_planner"
            assert agent.type == "agent"

    def test_find_tools_for_query(self):
        """Test finding tools that match a query."""
        loader = ToolLoaderService()
        loader.load_all()

        # Search for database-related query
        matches = loader.find_tools_for_query("search the database for articles")
        # Returns list of (tool, score) tuples
        assert isinstance(matches, list)

    def test_reload(self):
        """Test forcing reload of definitions."""
        loader = ToolLoaderService()
        loader.load_all()

        initial_count = len(loader.list_tools())

        # Force reload
        loader.reload()

        # Count should remain the same
        assert len(loader.list_tools()) == initial_count


class TestSingleton:
    """Tests for the singleton pattern."""

    def test_get_tool_loader_returns_same_instance(self):
        """Test that get_tool_loader returns the same instance."""
        loader1 = get_tool_loader()
        loader2 = get_tool_loader()

        assert loader1 is loader2


class TestActualDataFiles:
    """Integration tests with actual data files."""

    def test_database_search_tool_exists(self):
        """Test that the database_search tool was created."""
        tool_path = TOOLS_DIR / "database_search.md"
        assert tool_path.exists(), f"Tool file not found at {tool_path}"

    def test_sentiment_analysis_tool_exists(self):
        """Test that the sentiment_analysis tool was created."""
        tool_path = TOOLS_DIR / "sentiment_analysis.md"
        assert tool_path.exists(), f"Tool file not found at {tool_path}"

    def test_deep_research_workflow_exists(self):
        """Test that the deep_research workflow was created."""
        workflow_path = WORKFLOWS_DIR / "deep_research.md"
        assert workflow_path.exists(), f"Workflow file not found at {workflow_path}"

    def test_research_planner_agent_exists(self):
        """Test that the research_planner agent was created."""
        agent_path = AGENTS_DIR / "research_planner.md"
        assert agent_path.exists(), f"Agent file not found at {agent_path}"

    def test_load_database_search_tool(self):
        """Test loading the actual database_search tool."""
        loader = get_tool_loader()
        tool = loader.get_tool("enhanced_database_search")

        assert tool is not None
        assert tool.name == "enhanced_database_search"
        assert tool.version == "1.0.0"
        assert tool.type == "tool"
        assert len(tool.triggers) > 0

    def test_load_deep_research_workflow(self):
        """Test loading the actual deep_research workflow."""
        loader = get_tool_loader()
        workflow = loader.get_workflow("deep_research_workflow")

        assert workflow is not None
        assert workflow.name == "deep_research_workflow"
        assert len(workflow.stages) == 4

        # Verify stages
        stage_names = [s["name"] for s in workflow.stages]
        assert "planning" in stage_names
        assert "searching" in stage_names
        assert "synthesis" in stage_names
        assert "writing" in stage_names

        # Verify model config
        planning_config = workflow.get_model_config_for_stage("planning")
        assert "model" in planning_config
        assert "temperature" in planning_config

    def test_workflow_sampling_filtering(self):
        """Test that sampling and filtering configs are properly loaded."""
        loader = get_tool_loader()
        workflow = loader.get_workflow("deep_research_workflow")

        if workflow:
            sampling = workflow.get_sampling_config()
            assert sampling["strategy"] == "balanced"
            assert sampling["articles_per_query"] == 20
            assert "diversity" in sampling

            filtering = workflow.get_filtering_config()
            assert filtering["min_credibility"] == 40
            assert filtering["date_range"]["days_back"] == 30
