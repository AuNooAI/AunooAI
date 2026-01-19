"""
Conversation Compactor for Auspex.

Provides intelligent conversation compaction to manage long conversations:
- Keeps last N turns in full detail
- Summarizes older messages using LLM
- Tracks context quality metrics
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import litellm

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_RECENT_TURNS_TO_KEEP = 6  # Keep last 6 turns (3 user + 3 assistant) in full
DEFAULT_TOKEN_THRESHOLD = 50000  # Start compaction above 50k tokens
CHARS_PER_TOKEN = 4  # Conservative estimate
SUMMARY_MODEL = "gpt-4.1-mini"  # Fast model for summarization
MAX_SUMMARY_TOKENS = 2000  # Max tokens for the summary


@dataclass
class CompactionMetrics:
    """Metrics for conversation compaction."""
    original_messages: int = 0
    compacted_messages: int = 0
    original_tokens_estimate: int = 0
    compacted_tokens_estimate: int = 0
    summarized_turns: int = 0
    recent_turns_kept: int = 0
    compaction_applied: bool = False
    compaction_timestamp: Optional[datetime] = None


@dataclass
class CompactedConversation:
    """Result of conversation compaction."""
    messages: List[Dict]
    metrics: CompactionMetrics
    summary_context: Optional[str] = None


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """Estimate total tokens in a list of messages."""
    total = 0
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            # Handle multi-part content
            for part in content:
                if isinstance(part, dict) and 'text' in part:
                    total += estimate_tokens(part['text'])
    return total


def needs_compaction(
    messages: List[Dict],
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD
) -> bool:
    """
    Check if conversation needs compaction.

    Args:
        messages: List of conversation messages
        token_threshold: Token count above which to trigger compaction

    Returns:
        True if compaction is needed
    """
    if not messages:
        return False

    total_tokens = estimate_messages_tokens(messages)
    should_compact = total_tokens > token_threshold

    if should_compact:
        logger.info(
            f"Compaction needed: {total_tokens} estimated tokens > {token_threshold} threshold"
        )

    return should_compact


async def summarize_conversation_segment(
    messages: List[Dict],
    topic_context: Optional[str] = None
) -> str:
    """
    Summarize a segment of conversation using LLM.

    Args:
        messages: Messages to summarize
        topic_context: Optional topic for context

    Returns:
        Summary text
    """
    if not messages:
        return ""

    # Build the conversation text
    conversation_parts = []
    for msg in messages:
        role = msg.get('role', 'unknown').upper()
        content = msg.get('content', '')

        # Skip system messages
        if role == 'SYSTEM':
            continue

        # Truncate very long messages for summarization
        if len(content) > 2000:
            content = content[:2000] + "..."

        conversation_parts.append(f"{role}: {content}")

    conversation_text = "\n\n".join(conversation_parts)

    # Create summarization prompt
    prompt = f"""Summarize the following conversation between a user and an AI research assistant.
Focus on:
1. Key questions asked by the user
2. Important findings and data points discovered
3. Any conclusions or insights reached
4. Topics and entities discussed

Keep the summary concise but preserve critical information that would be needed to continue the conversation meaningfully.

{"Topic context: " + topic_context if topic_context else ""}

CONVERSATION:
{conversation_text}

SUMMARY:"""

    try:
        response = await litellm.acompletion(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=MAX_SUMMARY_TOKENS
        )

        summary = response.choices[0].message.content.strip()
        logger.info(f"Generated conversation summary: {len(summary)} chars")
        return summary

    except Exception as e:
        logger.error(f"Error summarizing conversation: {e}")
        # Fallback to basic summary
        return _create_basic_summary(messages)


def _create_basic_summary(messages: List[Dict]) -> str:
    """Create a basic summary without LLM when summarization fails."""
    user_messages = [m for m in messages if m.get('role') == 'user']
    assistant_messages = [m for m in messages if m.get('role') == 'assistant']

    summary_parts = [f"[Previous conversation: {len(user_messages)} user messages, {len(assistant_messages)} assistant responses]"]

    # Include first user question
    if user_messages:
        first_q = user_messages[0].get('content', '')[:200]
        summary_parts.append(f"Initial question: {first_q}...")

    # Include last assistant response snippet
    if assistant_messages:
        last_a = assistant_messages[-1].get('content', '')[:300]
        summary_parts.append(f"Last discussed: {last_a}...")

    return "\n".join(summary_parts)


async def compact_conversation(
    messages: List[Dict],
    recent_turns_to_keep: int = DEFAULT_RECENT_TURNS_TO_KEEP,
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
    topic_context: Optional[str] = None
) -> CompactedConversation:
    """
    Compact a conversation by summarizing older messages.

    Args:
        messages: Full list of conversation messages
        recent_turns_to_keep: Number of recent turns to keep in full
        token_threshold: Token threshold for triggering compaction
        topic_context: Optional topic for context in summarization

    Returns:
        CompactedConversation with compacted messages and metrics
    """
    metrics = CompactionMetrics(
        original_messages=len(messages),
        original_tokens_estimate=estimate_messages_tokens(messages)
    )

    # Check if compaction is needed
    if not needs_compaction(messages, token_threshold):
        metrics.compaction_applied = False
        metrics.compacted_messages = len(messages)
        metrics.compacted_tokens_estimate = metrics.original_tokens_estimate
        return CompactedConversation(messages=messages, metrics=metrics)

    # Separate system messages (keep all)
    system_messages = [m for m in messages if m.get('role') == 'system']
    conversation_messages = [m for m in messages if m.get('role') != 'system']

    # Calculate how many messages to keep (recent turns)
    # A "turn" is typically a user message + assistant response
    messages_to_keep = recent_turns_to_keep * 2  # user + assistant

    if len(conversation_messages) <= messages_to_keep:
        # Not enough messages to compact
        metrics.compaction_applied = False
        metrics.compacted_messages = len(messages)
        metrics.compacted_tokens_estimate = metrics.original_tokens_estimate
        metrics.recent_turns_kept = len(conversation_messages) // 2
        return CompactedConversation(messages=messages, metrics=metrics)

    # Split messages
    older_messages = conversation_messages[:-messages_to_keep]
    recent_messages = conversation_messages[-messages_to_keep:]

    # Summarize older messages
    summary = await summarize_conversation_segment(older_messages, topic_context)

    # Create summary message
    summary_message = {
        "role": "assistant",
        "content": f"[CONVERSATION SUMMARY - Earlier discussion summarized for context]\n\n{summary}\n\n[END SUMMARY - Recent messages follow]"
    }

    # Build compacted message list
    compacted = system_messages + [summary_message] + recent_messages

    # Update metrics
    metrics.compaction_applied = True
    metrics.compacted_messages = len(compacted)
    metrics.compacted_tokens_estimate = estimate_messages_tokens(compacted)
    metrics.summarized_turns = len(older_messages) // 2
    metrics.recent_turns_kept = len(recent_messages) // 2
    metrics.compaction_timestamp = datetime.now()

    logger.info(
        f"Compacted conversation: {metrics.original_messages} -> {metrics.compacted_messages} messages, "
        f"~{metrics.original_tokens_estimate} -> ~{metrics.compacted_tokens_estimate} tokens"
    )

    return CompactedConversation(
        messages=compacted,
        metrics=metrics,
        summary_context=summary
    )


def get_compaction_status(metrics: CompactionMetrics) -> Dict:
    """
    Get human-readable compaction status.

    Args:
        metrics: Compaction metrics

    Returns:
        Status dictionary
    """
    return {
        "compaction_applied": metrics.compaction_applied,
        "original_messages": metrics.original_messages,
        "compacted_messages": metrics.compacted_messages,
        "tokens_saved": metrics.original_tokens_estimate - metrics.compacted_tokens_estimate,
        "compression_ratio": round(
            metrics.compacted_tokens_estimate / max(metrics.original_tokens_estimate, 1),
            2
        ),
        "summarized_turns": metrics.summarized_turns,
        "recent_turns_kept": metrics.recent_turns_kept,
        "timestamp": metrics.compaction_timestamp.isoformat() if metrics.compaction_timestamp else None
    }
