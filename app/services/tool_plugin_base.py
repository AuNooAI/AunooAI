"""
Pluggable Tool System for Auspex

This module provides the base classes and registry for creating pluggable tools
that can be dropped into folders and automatically discovered by Auspex.

Tool Structure:
    data/auspex/plugins/<tool_name>/
    ├── tool.md       # YAML frontmatter with metadata + markdown documentation
    ├── config.json   # Optional configuration (thresholds, models, etc.)
    └── handler.py    # Python class implementing ToolHandler

Example handler.py:
    from app.services.tool_plugin_base import ToolHandler, ToolResult

    class MyToolHandler(ToolHandler):
        async def execute(self, params: dict, context: dict) -> ToolResult:
            # Your tool logic here
            return ToolResult(
                success=True,
                data={"result": "..."},
                message="Tool executed successfully"
            )
"""

import abc
import json
import logging
import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Callable, Union
import yaml
import re

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standard result object returned by all tools."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str  # string, integer, float, boolean, array, object
    required: bool = False
    default: Any = None
    description: str = ""
    enum: Optional[List[str]] = None  # For constrained values

    @classmethod
    def from_dict(cls, data: Dict) -> "ToolParameter":
        return cls(
            name=data.get("name", ""),
            type=data.get("type", "string"),
            required=data.get("required", False),
            default=data.get("default"),
            description=data.get("description", ""),
            enum=data.get("enum")
        )


@dataclass
class TriggerPattern:
    """Pattern for matching user queries to tools."""
    patterns: List[str]
    priority: str = "medium"  # high, medium, low

    @property
    def priority_score(self) -> float:
        return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(self.priority, 0.5)

    def matches(self, query: str) -> tuple[bool, float]:
        """Check if query matches any pattern."""
        query_lower = query.lower()
        for pattern in self.patterns:
            try:
                if re.search(pattern, query_lower):
                    return True, self.priority_score
            except re.error:
                # Fallback to simple substring match
                if pattern.lower() in query_lower:
                    return True, self.priority_score
        return False, 0.0


@dataclass
class ToolDefinition:
    """Complete definition of a pluggable tool."""
    name: str
    version: str
    description: str
    category: str
    parameters: List[ToolParameter]
    triggers: List[TriggerPattern]
    output_schema: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    documentation: str = ""
    plugin_path: Optional[Path] = None
    handler_class: Optional[Type["ToolHandler"]] = None
    # Prompt-only tool fields
    prompt: str = ""  # The LLM prompt to use
    actions: List[str] = field(default_factory=list)  # Actions to perform: vector_search, db_search, web_search, etc.
    is_prompt_tool: bool = False  # True if this is a prompt-only tool (no handler.py)
    requires_api_key: Optional[str] = None  # API key required for this tool (checks env var)

    def matches_query(self, query: str) -> tuple[bool, float]:
        """Check if this tool should handle the given query."""
        best_match = False
        best_score = 0.0
        for trigger in self.triggers:
            matches, score = trigger.matches(query)
            if matches and score > best_score:
                best_match = True
                best_score = score
        return best_match, best_score

    def validate_params(self, params: Dict) -> tuple[bool, List[str]]:
        """Validate parameters against the definition."""
        errors = []
        for param in self.parameters:
            if param.required and param.name not in params:
                errors.append(f"Missing required parameter: {param.name}")
            if param.name in params and param.enum:
                if params[param.name] not in param.enum:
                    errors.append(f"Invalid value for {param.name}. Must be one of: {param.enum}")
        return len(errors) == 0, errors

    def get_params_with_defaults(self, params: Dict) -> Dict:
        """Fill in default values for missing optional parameters."""
        result = dict(params)
        for param in self.parameters:
            if param.name not in result and param.default is not None:
                result[param.name] = param.default
        return result

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description
                }
                for p in self.parameters
            ],
            "triggers": [
                {"patterns": t.patterns, "priority": t.priority}
                for t in self.triggers
            ]
        }


class ToolHandler(abc.ABC):
    """
    Base class for tool handlers.

    Subclass this to create a new tool. Implement the execute() method
    with your tool's logic.
    """

    def __init__(self, definition: ToolDefinition, config: Dict[str, Any] = None):
        self.definition = definition
        self.config = config or {}
        self.logger = logging.getLogger(f"tool.{definition.name}")

    @abc.abstractmethod
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            params: Tool parameters (already validated and with defaults filled)
            context: Execution context containing:
                - topic: Current topic
                - user: Username
                - chat_id: Current chat ID (if applicable)
                - db: Database instance
                - vector_store: Vector store instance
                - ai_model: Function to get AI model

        Returns:
            ToolResult with the execution outcome
        """
        pass

    def get_help(self) -> str:
        """Return help text for this tool."""
        return self.definition.documentation or self.definition.description


class PromptToolHandler(ToolHandler):
    """
    Handler for prompt-only tools defined via .md files.

    These tools use built-in actions (vector_search, db_search, web_search)
    combined with an LLM prompt to perform analysis.

    Supported actions:
    - vector_search: Semantic search using vector embeddings
    - db_search: SQL-based search with filters
    - web_search: External news API search (if configured)
    - sentiment_analysis: Analyze sentiment distribution
    - bias_analysis: Analyze political/media bias
    """

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Execute a prompt-based tool using configured actions and LLM."""
        import time
        start_time = time.time()

        topic = params.get('topic') or context.get('topic', '')
        query = params.get('query', '')
        limit = params.get('limit', 50)

        db = context.get('db')
        vector_search = context.get('vector_store')
        ai_model_getter = context.get('ai_model')

        if not db:
            return ToolResult(
                success=False,
                error="Database not available"
            )

        # Collect data from actions
        action_results = {}
        articles = []

        for action in self.definition.actions:
            try:
                if action == 'vector_search' and vector_search:
                    # Semantic search
                    search_query = query or topic
                    results = vector_search(
                        query=search_query,
                        top_k=limit,
                        metadata_filter={"topic": topic} if topic else None
                    )
                    if results:
                        articles.extend(results)
                        action_results['vector_search'] = {
                            'count': len(results),
                            'method': 'semantic'
                        }

                elif action == 'db_search' and db:
                    # Database search
                    db_articles, count = db.search_articles(
                        topic=topic,
                        keyword=query,
                        page=1,
                        per_page=limit
                    )
                    if db_articles:
                        # Deduplicate with vector results
                        existing_ids = {a.get('id') for a in articles if a.get('id')}
                        new_articles = [a for a in db_articles if a.get('id') not in existing_ids]
                        articles.extend(new_articles)
                        action_results['db_search'] = {
                            'count': len(db_articles),
                            'new_added': len(new_articles)
                        }

                elif action == 'sentiment_analysis' and db:
                    # Get sentiment distribution
                    sentiment_data = self._get_sentiment_distribution(db, topic, articles)
                    action_results['sentiment'] = sentiment_data

                elif action == 'bias_analysis' and db:
                    # Get political bias distribution
                    bias_data = self._get_bias_distribution(db, topic, articles)
                    action_results['bias'] = bias_data

                elif action == 'web_search':
                    # Google Programmable Search Engine
                    web_results = await self._execute_web_search(query or topic, limit)
                    if web_results:
                        action_results['web_search'] = web_results

            except Exception as e:
                self.logger.error(f"Action {action} failed: {e}")
                action_results[action] = {'error': str(e)}

        # Build context for LLM prompt
        article_context = self._format_articles_for_prompt(articles[:limit])

        # Execute LLM prompt if provided
        llm_response = None
        if self.definition.prompt and ai_model_getter:
            try:
                # Build the full prompt
                full_prompt = self.definition.prompt.format(
                    topic=topic,
                    query=query,
                    article_count=len(articles),
                    articles=article_context,
                    **action_results
                )

                # Get AI model and execute
                model = ai_model_getter()
                if model:
                    llm_response = await self._execute_llm(model, full_prompt, context)
            except Exception as e:
                self.logger.error(f"LLM execution failed: {e}")
                llm_response = f"Analysis error: {str(e)}"

        execution_time = int((time.time() - start_time) * 1000)

        return ToolResult(
            success=True,
            data={
                'analysis': llm_response or self._generate_basic_analysis(action_results, articles),
                'article_count': len(articles),
                'actions_performed': list(action_results.keys()),
                'action_results': action_results
            },
            message=f"Analyzed {len(articles)} articles using {len(action_results)} actions",
            execution_time_ms=execution_time
        )

    def _get_sentiment_distribution(self, db, topic: str, articles: List[Dict]) -> Dict:
        """Calculate sentiment distribution from articles."""
        from collections import Counter

        sentiments = Counter()
        for article in articles:
            sentiment = article.get('sentiment', 'Unknown')
            sentiments[sentiment] += 1

        total = sum(sentiments.values())
        return {
            'distribution': dict(sentiments),
            'percentages': {k: round(v/total*100, 1) for k, v in sentiments.items()} if total > 0 else {},
            'total_articles': total,
            'dominant': sentiments.most_common(1)[0][0] if sentiments else 'Unknown'
        }

    def _get_bias_distribution(self, db, topic: str, articles: List[Dict]) -> Dict:
        """Calculate political bias distribution from articles."""
        from collections import Counter

        biases = Counter()
        bias_scores = []

        for article in articles:
            # Check for bias fields (from media_bias enrichment)
            bias = article.get('political_bias') or article.get('bias') or article.get('media_bias', 'Unknown')
            biases[bias] += 1

            # Collect numeric bias scores if available
            score = article.get('bias_score')
            if score is not None:
                bias_scores.append(score)

        total = sum(biases.values())
        avg_score = sum(bias_scores) / len(bias_scores) if bias_scores else None

        return {
            'distribution': dict(biases),
            'percentages': {k: round(v/total*100, 1) for k, v in biases.items()} if total > 0 else {},
            'total_articles': total,
            'average_bias_score': round(avg_score, 2) if avg_score else None,
            'dominant': biases.most_common(1)[0][0] if biases else 'Unknown'
        }

    def _format_articles_for_prompt(self, articles: List[Dict], max_chars: int = 8000) -> str:
        """Format articles for LLM context."""
        lines = []
        char_count = 0

        for i, article in enumerate(articles, 1):
            title = article.get('title', 'Untitled')
            summary = article.get('summary', '')[:200]
            source = article.get('news_source', 'Unknown')
            sentiment = article.get('sentiment', '')
            bias = article.get('political_bias') or article.get('media_bias', '')

            line = f"{i}. [{source}] {title}"
            if sentiment:
                line += f" (Sentiment: {sentiment})"
            if bias:
                line += f" (Bias: {bias})"
            if summary:
                line += f"\n   {summary}"

            if char_count + len(line) > max_chars:
                lines.append(f"... and {len(articles) - i + 1} more articles")
                break

            lines.append(line)
            char_count += len(line)

        return "\n".join(lines)

    async def _execute_llm(self, model, prompt: str, context: Dict) -> str:
        """Execute LLM with the prompt."""
        try:
            # Try async completion first
            if hasattr(model, 'acomplete'):
                response = await model.acomplete(prompt)
                return response.text if hasattr(response, 'text') else str(response)
            elif hasattr(model, 'complete'):
                response = model.complete(prompt)
                return response.text if hasattr(response, 'text') else str(response)
            else:
                # Fallback: assume it's a callable
                response = model(prompt)
                return str(response)
        except Exception as e:
            self.logger.error(f"LLM execution error: {e}")
            return f"Analysis could not be completed: {str(e)}"

    def _generate_basic_analysis(self, action_results: Dict, articles: List[Dict]) -> str:
        """Generate basic analysis when LLM is not available."""
        parts = [f"Analyzed {len(articles)} articles."]

        if 'sentiment' in action_results:
            sent = action_results['sentiment']
            parts.append(f"\nSentiment: {sent.get('dominant', 'Unknown')} dominant "
                        f"({sent.get('percentages', {})})")

        if 'bias' in action_results:
            bias = action_results['bias']
            parts.append(f"\nBias: {bias.get('dominant', 'Unknown')} dominant "
                        f"({bias.get('percentages', {})})")

        if 'web_search' in action_results:
            web = action_results['web_search']
            parts.append(f"\nWeb Search: Found {web.get('total_results', 0)} results")

        return "\n".join(parts)

    async def _execute_web_search(self, query: str, limit: int = 10) -> Optional[Dict]:
        """Execute Google Programmable Search Engine query."""
        import os
        import aiohttp

        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GOOGLE_SEARCH_API_KEY')
        search_engine_id = os.environ.get('GOOGLE_CSE_ID') or os.environ.get('GOOGLE_SEARCH_ENGINE_ID')

        if not api_key or not search_engine_id:
            self.logger.debug("Google Search API key or CSE ID not configured")
            return None

        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': api_key,
                'cx': search_engine_id,
                'q': query,
                'num': min(limit, 10)  # Google CSE max is 10 per request
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        self.logger.error(f"Google Search API error: {response.status}")
                        return None

                    data = await response.json()

            results = []
            for item in data.get('items', []):
                results.append({
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'source': item.get('displayLink', '')
                })

            return {
                'results': results,
                'total_results': int(data.get('searchInformation', {}).get('totalResults', 0)),
                'query': query
            }

        except Exception as e:
            self.logger.error(f"Google Search failed: {e}")
            return None


class ToolRegistry:
    """
    Registry for discovering and managing pluggable tools.

    Scans plugin directories, loads tool definitions and handlers,
    and provides routing based on query patterns.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, ToolHandler] = {}
        self._loaded = False
        self._plugin_dirs: List[Path] = []

    def add_plugin_directory(self, path: Union[str, Path]):
        """Add a directory to scan for plugins."""
        self._plugin_dirs.append(Path(path))

    def load_all(self) -> int:
        """
        Load all tools from plugin directories.

        Returns:
            Number of tools successfully loaded
        """
        loaded_count = 0

        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                logger.warning(f"Plugin directory does not exist: {plugin_dir}")
                continue

            # Scan for plugin folders (each containing tool.md, handler.py)
            for item in plugin_dir.iterdir():
                if item.is_dir() and not item.name.startswith("_"):
                    try:
                        if self._load_plugin(item):
                            loaded_count += 1
                    except Exception as e:
                        logger.error(f"Failed to load plugin from {item}: {e}")

        self._loaded = True
        logger.info(f"Loaded {loaded_count} plugins from {len(self._plugin_dirs)} directories")
        return loaded_count

    def _load_plugin(self, plugin_path: Path) -> bool:
        """Load a single plugin from its directory."""
        tool_md = plugin_path / "tool.md"
        handler_py = plugin_path / "handler.py"
        config_json = plugin_path / "config.json"

        if not tool_md.exists():
            logger.debug(f"Skipping {plugin_path}: no tool.md found")
            return False

        # Parse tool.md (YAML frontmatter + markdown)
        definition = self._parse_tool_definition(tool_md)
        if not definition:
            return False

        definition.plugin_path = plugin_path

        # Check if required API key is present
        if definition.requires_api_key:
            import os
            api_key = os.environ.get(definition.requires_api_key)
            if not api_key:
                logger.info(f"Skipping plugin {definition.name}: required API key '{definition.requires_api_key}' not configured")
                return False

        # Load optional config.json
        if config_json.exists():
            try:
                with open(config_json, 'r') as f:
                    definition.config = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config.json for {definition.name}: {e}")

        # Load handler.py or use PromptToolHandler for prompt-only tools
        handler_class = None
        if handler_py.exists():
            handler_class = self._load_handler_class(handler_py, definition.name)
            definition.handler_class = handler_class

        # Register the tool
        self._tools[definition.name] = definition

        # Instantiate handler
        if handler_class:
            # Custom handler from handler.py
            try:
                handler = handler_class(definition, definition.config)
                self._handlers[definition.name] = handler
                logger.info(f"Loaded plugin: {definition.name} v{definition.version} with custom handler")
            except Exception as e:
                logger.error(f"Failed to instantiate handler for {definition.name}: {e}")
        elif definition.is_prompt_tool:
            # Prompt-only tool - use PromptToolHandler
            try:
                handler = PromptToolHandler(definition, definition.config)
                self._handlers[definition.name] = handler
                logger.info(f"Loaded plugin: {definition.name} v{definition.version} with prompt handler (actions: {definition.actions})")
            except Exception as e:
                logger.error(f"Failed to instantiate prompt handler for {definition.name}: {e}")
        else:
            logger.info(f"Loaded plugin definition: {definition.name} v{definition.version} (no handler)")

        return True

    def _parse_tool_definition(self, tool_md: Path) -> Optional[ToolDefinition]:
        """Parse tool.md file with YAML frontmatter."""
        try:
            with open(tool_md, 'r') as f:
                content = f.read()

            # Split frontmatter and markdown
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    documentation = parts[2].strip()
                else:
                    return None
            else:
                return None

            # Parse parameters
            parameters = []
            for p in frontmatter.get('parameters', []):
                parameters.append(ToolParameter.from_dict(p))

            # Parse triggers
            triggers = []
            for t in frontmatter.get('triggers', []):
                triggers.append(TriggerPattern(
                    patterns=t.get('patterns', []),
                    priority=t.get('priority', 'medium')
                ))

            # Get prompt and actions for prompt-only tools
            prompt = frontmatter.get('prompt', '')
            actions = frontmatter.get('actions', [])
            is_prompt_tool = bool(prompt or actions)
            requires_api_key = frontmatter.get('requires_api_key')

            return ToolDefinition(
                name=frontmatter.get('name', tool_md.parent.name),
                version=frontmatter.get('version', '1.0.0'),
                description=frontmatter.get('description', ''),
                category=frontmatter.get('category', 'general'),
                parameters=parameters,
                triggers=triggers,
                output_schema=frontmatter.get('output', {}),
                documentation=documentation,
                prompt=prompt,
                actions=actions,
                is_prompt_tool=is_prompt_tool,
                requires_api_key=requires_api_key
            )

        except Exception as e:
            logger.error(f"Failed to parse {tool_md}: {e}")
            return None

    def _load_handler_class(self, handler_py: Path, tool_name: str) -> Optional[Type[ToolHandler]]:
        """Dynamically load handler class from handler.py."""
        try:
            # Create a unique module name
            module_name = f"auspex_plugin_{tool_name}"

            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, handler_py)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find the handler class (subclass of ToolHandler)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, ToolHandler) and
                    attr is not ToolHandler):
                    return attr

            logger.warning(f"No ToolHandler subclass found in {handler_py}")
            return None

        except Exception as e:
            logger.error(f"Failed to load handler from {handler_py}: {e}")
            return None

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Optional[ToolHandler]:
        """Get a tool handler by name."""
        return self._handlers.get(name)

    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tool definitions."""
        return list(self._tools.values())

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get tools filtered by category."""
        return [t for t in self._tools.values() if t.category == category]

    def find_matching_tools(self, query: str, min_score: float = 0.3) -> List[tuple[ToolDefinition, float]]:
        """
        Find tools that match the given query.

        Returns:
            List of (tool_definition, match_score) tuples, sorted by score descending
        """
        matches = []
        for tool in self._tools.values():
            is_match, score = tool.matches_query(query)
            if is_match and score >= min_score:
                matches.append((tool, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def find_best_tool(self, query: str) -> Optional[tuple[ToolDefinition, float]]:
        """Find the best matching tool for a query."""
        matches = self.find_matching_tools(query)
        return matches[0] if matches else None

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters to pass to the tool
            context: Execution context

        Returns:
            ToolResult with execution outcome
        """
        import time

        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        handler = self.get_handler(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                error=f"No handler available for tool: {tool_name}"
            )

        # Validate and fill defaults
        is_valid, errors = tool.validate_params(params)
        if not is_valid:
            return ToolResult(
                success=False,
                error=f"Invalid parameters: {', '.join(errors)}"
            )

        params_with_defaults = tool.get_params_with_defaults(params)

        # Execute with timing
        start_time = time.time()
        try:
            result = await handler.execute(params_with_defaults, context)
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

    def get_tools_for_llm(self) -> List[Dict]:
        """
        Get tool definitions formatted for LLM function calling.

        Returns a list of tool schemas compatible with OpenAI/Anthropic function calling.
        """
        tools = []
        for tool in self._tools.values():
            # Convert to function calling format
            properties = {}
            required = []

            for param in tool.parameters:
                prop = {
                    "type": param.type,
                    "description": param.description
                }
                if param.enum:
                    prop["enum"] = param.enum
                properties[param.name] = prop

                if param.required:
                    required.append(param.name)

            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })

        return tools


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # Add default plugin directories
        base_path = Path(__file__).parent.parent.parent / "data" / "auspex"
        _registry.add_plugin_directory(base_path / "plugins")
        _registry.add_plugin_directory(base_path / "tools")  # Legacy support
    return _registry


def init_tool_registry() -> ToolRegistry:
    """Initialize and load the tool registry."""
    registry = get_tool_registry()
    if not registry._loaded:
        registry.load_all()
    return registry
