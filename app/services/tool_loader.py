"""
Tool Loader Service
Loads and manages tool, workflow, and agent definitions from markdown files.

Tools, workflows, and agents are defined in markdown files with YAML frontmatter
in the data/auspex/ directory structure:
  - data/auspex/tools/      - Individual tool definitions
  - data/auspex/workflows/  - Multi-step workflow definitions
  - data/auspex/agents/     - Agent persona definitions
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

try:
    import frontmatter
except ImportError:
    frontmatter = None
    logging.warning("python-frontmatter not installed. Tool definitions will not load.")

logger = logging.getLogger(__name__)

# Base directory for auspex tool definitions
BASE_DIR = Path(__file__).parent.parent.parent / "data" / "auspex"
TOOLS_DIR = BASE_DIR / "tools"
WORKFLOWS_DIR = BASE_DIR / "workflows"
AGENTS_DIR = BASE_DIR / "agents"


@dataclass
class ToolDefinition:
    """Represents a loaded tool definition from a markdown file."""

    name: str
    version: str
    type: str  # "tool", "workflow", or "agent"
    description: str
    content: str  # The markdown body content
    metadata: Dict[str, Any] = field(default_factory=dict)
    parameters: List[Dict] = field(default_factory=list)
    triggers: List[Dict] = field(default_factory=list)
    file_path: Optional[Path] = None

    @classmethod
    def from_file(cls, path: Path) -> "ToolDefinition":
        """Load a tool definition from a markdown file with YAML frontmatter."""
        if frontmatter is None:
            raise ImportError("python-frontmatter is required to load tool definitions")

        post = frontmatter.load(path)

        return cls(
            name=post.metadata.get("name", path.stem),
            version=post.metadata.get("version", "1.0.0"),
            type=post.metadata.get("type", "tool"),
            description=post.metadata.get("description", ""),
            content=post.content,
            metadata=dict(post.metadata),
            parameters=post.metadata.get("parameters", []),
            triggers=post.metadata.get("triggers", []),
            file_path=path
        )

    def matches_query(self, query: str) -> tuple[bool, float]:
        """
        Check if this tool should be triggered for a given query.

        Returns:
            Tuple of (matches, priority_score)
            priority_score is higher for better matches (0.0 - 1.0)
        """
        query_lower = query.lower()

        for trigger in self.triggers:
            patterns = trigger.get("patterns", [])
            priority = trigger.get("priority", "medium")

            priority_score = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(priority, 0.5)

            for pattern in patterns:
                try:
                    if re.search(pattern, query_lower, re.IGNORECASE):
                        return True, priority_score
                except re.error:
                    # Treat as literal string if not valid regex
                    if pattern.lower() in query_lower:
                        return True, priority_score

        return False, 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "description": self.description,
            "parameters": self.parameters,
            "triggers": self.triggers,
            "content": self.content
        }


@dataclass
class WorkflowDefinition:
    """Represents a loaded workflow definition with multiple stages."""

    name: str
    version: str
    description: str
    stages: List[Dict]
    config: Dict[str, Any]
    sampling: Dict[str, Any]
    filtering: Dict[str, Any]
    model_config: Dict[str, Any]
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[Path] = None

    @classmethod
    def from_file(cls, path: Path) -> "WorkflowDefinition":
        """Load a workflow definition from a markdown file with YAML frontmatter."""
        if frontmatter is None:
            raise ImportError("python-frontmatter is required to load workflow definitions")

        post = frontmatter.load(path)

        return cls(
            name=post.metadata.get("name", path.stem),
            version=post.metadata.get("version", "1.0.0"),
            description=post.metadata.get("description", ""),
            stages=post.metadata.get("stages", []),
            config=post.metadata.get("config", {}),
            sampling=post.metadata.get("sampling", {}),
            filtering=post.metadata.get("filtering", {}),
            model_config=post.metadata.get("model_config", {}),
            content=post.content,
            metadata=dict(post.metadata),
            file_path=path
        )

    def get_stage(self, stage_name: str) -> Optional[Dict]:
        """Get a specific stage by name."""
        for stage in self.stages:
            if stage.get("name") == stage_name:
                return stage
        return None

    def get_model_config_for_stage(self, stage_name: str) -> Dict[str, Any]:
        """
        Get the model configuration for a specific stage.
        Merges preset defaults with stage-specific overrides.
        """
        # Get preset configuration
        preset_name = self.model_config.get("preset", "balanced")
        presets = self.model_config.get("presets", {})
        preset_config = presets.get(preset_name, {})

        # Get stage-specific overrides
        stages_config = self.model_config.get("stages", {})
        stage_config = stages_config.get(stage_name, {})

        # Merge: preset defaults < stage overrides
        merged = {**preset_config, **stage_config}

        # Remove non-model fields
        merged.pop("description", None)

        return merged

    def get_sampling_config(self) -> Dict[str, Any]:
        """Get the sampling configuration with defaults."""
        defaults = {
            "strategy": "balanced",
            "articles_per_query": 20,
            "max_total_articles": 100,
            "recency_weight": 0.3,
            "diversity": {
                "category_diversity": True,
                "sentiment_diversity": True,
                "source_diversity": True,
                "max_per_source": 5
            }
        }
        return {**defaults, **self.sampling}

    def get_filtering_config(self) -> Dict[str, Any]:
        """Get the filtering configuration with defaults."""
        defaults = {
            "min_credibility": 40,
            "date_range": {"enabled": True, "days_back": 30},
            "content_quality": {
                "min_summary_length": 50,
                "require_url": True,
                "exclude_duplicates": True
            },
            "relevance": {"enabled": True, "min_score": 0.5}
        }
        return {**defaults, **self.filtering}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "stages": self.stages,
            "config": self.config,
            "sampling": self.get_sampling_config(),
            "filtering": self.get_filtering_config(),
            "model_config": self.model_config,
            "content": self.content
        }


class ToolLoaderService:
    """Service for loading and managing tool/workflow definitions."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._agents: Dict[str, ToolDefinition] = {}
        self._loaded = False

        # Ensure directories exist on initialization
        self._ensure_directories()

    def _ensure_directories(self):
        """Create tool/workflow/agent directories if they don't exist."""
        for directory in [TOOLS_DIR, WORKFLOWS_DIR, AGENTS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

    def load_all(self, force: bool = False):
        """Load all tool, workflow, and agent definitions."""
        if self._loaded and not force:
            return

        if frontmatter is None:
            logger.error("Cannot load tools: python-frontmatter not installed")
            self._loaded = True
            return

        # Clear existing if forcing reload
        if force:
            self._tools.clear()
            self._workflows.clear()
            self._agents.clear()

        # Load tools
        if TOOLS_DIR.exists():
            for path in TOOLS_DIR.glob("**/*.md"):
                try:
                    tool = ToolDefinition.from_file(path)
                    self._tools[tool.name] = tool
                    logger.info(f"Loaded tool: {tool.name} v{tool.version}")
                except Exception as e:
                    logger.error(f"Failed to load tool {path}: {e}")

        # Load workflows
        if WORKFLOWS_DIR.exists():
            for path in WORKFLOWS_DIR.glob("**/*.md"):
                try:
                    workflow = WorkflowDefinition.from_file(path)
                    self._workflows[workflow.name] = workflow
                    logger.info(f"Loaded workflow: {workflow.name} v{workflow.version}")
                except Exception as e:
                    logger.error(f"Failed to load workflow {path}: {e}")

        # Load agents
        if AGENTS_DIR.exists():
            for path in AGENTS_DIR.glob("**/*.md"):
                try:
                    agent = ToolDefinition.from_file(path)
                    self._agents[agent.name] = agent
                    logger.info(f"Loaded agent: {agent.name} v{agent.version}")
                except Exception as e:
                    logger.error(f"Failed to load agent {path}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._tools)} tools, {len(self._workflows)} workflows, {len(self._agents)} agents")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a specific tool by name."""
        self.load_all()
        return self._tools.get(name)

    def get_workflow(self, name: str) -> Optional[WorkflowDefinition]:
        """Get a specific workflow by name."""
        self.load_all()
        return self._workflows.get(name)

    def get_agent(self, name: str) -> Optional[ToolDefinition]:
        """Get a specific agent by name."""
        self.load_all()
        return self._agents.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        self.load_all()
        return [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
                "type": t.type
            }
            for t in self._tools.values()
        ]

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all available workflows."""
        self.load_all()
        return [
            {
                "name": w.name,
                "version": w.version,
                "description": w.description,
                "stages": [s.get("name") for s in w.stages]
            }
            for w in self._workflows.values()
        ]

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents."""
        self.load_all()
        return [
            {
                "name": a.name,
                "version": a.version,
                "description": a.description,
                "type": a.type
            }
            for a in self._agents.values()
        ]

    def find_tools_for_query(self, query: str) -> List[tuple[ToolDefinition, float]]:
        """
        Find tools that match a given query based on triggers.

        Returns:
            List of (tool, priority_score) tuples, sorted by priority
        """
        self.load_all()
        matches = []

        for tool in self._tools.values():
            matched, score = tool.matches_query(query)
            if matched:
                matches.append((tool, score))

        # Sort by priority score (highest first)
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def reload(self):
        """Force reload all definitions."""
        logger.info("Reloading all tool definitions...")
        self.load_all(force=True)


# Singleton instance
_tool_loader_instance: Optional[ToolLoaderService] = None


def get_tool_loader() -> ToolLoaderService:
    """Get the global tool loader service instance."""
    global _tool_loader_instance
    if _tool_loader_instance is None:
        _tool_loader_instance = ToolLoaderService()
    return _tool_loader_instance
