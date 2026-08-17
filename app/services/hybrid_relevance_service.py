"""
Hybrid Relevance Service

Combines multiple approaches for robust relevance scoring:
1. Embedding similarity - Works for ANY topic (zero-shot)
2. Fine-tuned classifier - More accurate for known topics
3. LLM fallback - Most accurate, used when confidence is low

Scoring hierarchy:
- High confidence: Use hybrid (classifier + embedding)
- Medium confidence: Use embedding only
- Low confidence: Fall back to LLM

Usage:
    from app.services.hybrid_relevance_service import get_hybrid_relevance_service

    service = get_hybrid_relevance_service()
    result = service.score_relevance(
        topic="Climate Change Policy",
        title="New EPA regulations on carbon emissions",
        summary="The EPA announced new rules..."
    )
    # Returns: {
    #     "relevant": True,
    #     "score": 0.85,
    #     "embedding_score": 0.82,
    #     "classifier_score": 0.88,
    #     "method": "hybrid"
    # }
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # Fast, good quality
CLASSIFIER_WEIGHT = 0.6  # Weight for classifier when available
EMBEDDING_WEIGHT = 0.4   # Weight for embedding similarity
NEW_TOPIC_THRESHOLD = 100  # Minimum training samples to trust classifier
DEFAULT_THRESHOLD = 0.5
LLM_FALLBACK_THRESHOLD = 0.3  # Legacy constant, kept for reference

# Cross-encoder as an intermediate tier between classifier+embedding and LLM
# fallback. Gated by its own env flag so we can roll it out independently of
# the retrieval reranker (which shares the underlying model).
# score_pair returns a sigmoid probability, but NOT one spread over [0, 1] for
# this input: the reranker was trained on (search query, passage) pairs and a
# topic label is not a search query. Measured on REAL production documents
# (title + summary, the same string _compute_cross_encoder_score builds) from
# wileytest:
#
#   THEME topics  AUC 0.885   relevant median 0.0014   other median 0.00003
#   BRAND topics  AUC 0.478   relevant median 0.00043  other median 0.00055
#
# So the tier is theme-only (see the gate in score_relevance) and accept-only.
# Both restrictions are load-bearing:
#
#  1. The previous CE_LOW=0.10 sits above essentially the whole relevant
#     population — every relevant article measured scored below it. Enabling
#     the flag as shipped would have "confidently rejected" ~100% of relevant
#     articles with no LLM review. Only the default-off saved it.
#  2. There is no honest reject threshold at all: relevant and irrelevant both
#     live in 1e-5..1e-2, and the widest cut losing no relevant article is
#     itself the lowest relevant article. That is a coincidence, not a margin.
#
# The asymmetry is what settles it. A wrong "confident accept" costs one
# enrichment call. A wrong "confident reject" drops the article for good,
# because nothing downstream re-examines it — the exact failure mode that made
# news vanish from the observer agents. Only the safe direction is wired up.
#
# Beware measuring this on titles alone: title-only scoring reports a far
# rosier AUC than the production title+summary document, because the summary
# adds text the reranker cannot align to a topic label.
#
# Re-derive CE_HIGH with scripts/evaluate_ce_vs_llm_fallback.py after any
# reranker model change, and when user_relevance_feedback passes ~50 labels.
USE_CE_TIER = os.getenv("RELEVANCE_USE_CE_TIER", "false").lower() in {"1", "true", "yes"}
# On theme topics 0.05 accepts 28/199 relevant (14%) while wrongly accepting
# 2/114 irrelevant (1.8%) — a modest saving of LLM calls at a cost of at worst
# a couple of extra enrichments.
CE_HIGH = float(os.getenv("RELEVANCE_CE_HIGH", "0.05"))  # above → confident accept

# Both brand-topic naming conventions in use across tenants.
_BRAND_TOPIC_RE = re.compile(r'^Brand Monitoring\s+|\s-\sBrand Watch$', re.I)


class HybridRelevanceService:
    """
    Hybrid relevance scoring combining embeddings and classification.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if HybridRelevanceService._initialized:
            return

        self.embedding_model = None
        self.classifier = None
        self.classifier_tokenizer = None
        self.device = "cpu"

        self._embedding_loaded = False
        self._classifier_loaded = False
        self._topic_cache = {}  # Cache topic embeddings
        self._known_topics = set()  # Topics seen in training

        HybridRelevanceService._initialized = True

    def _load_embedding_model(self) -> bool:
        """Load the sentence embedding model."""
        if self._embedding_loaded:
            return True

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {EMBEDDING_MODEL} (CPU mode)")
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
            self._embedding_loaded = True
            logger.info("Embedding model loaded successfully on CPU")
            return True

        except ImportError:
            logger.warning("sentence-transformers not installed. Run: pip install sentence-transformers")
            return False
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return False

    def _load_classifier(self) -> bool:
        """Load the fine-tuned relevance classifier."""
        if self._classifier_loaded:
            return True

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            import json

            model_path = Path(__file__).parent.parent.parent / "models" / "relevance_classifier" / "final"

            if not model_path.exists():
                logger.warning(f"Classifier not found at {model_path}")
                return False

            logger.info(f"Loading classifier from {model_path}")
            self.classifier_tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            self.classifier = AutoModelForSequenceClassification.from_pretrained(str(model_path))
            self.classifier.eval()

            # Load known topics from training data
            config_path = model_path / "model_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                    # Could store known topics in config

            self._classifier_loaded = True
            logger.info("Classifier loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load classifier: {e}")
            return False

    def load_models(self) -> Dict[str, bool]:
        """Load all models."""
        return {
            "embedding": self._load_embedding_model(),
            "classifier": self._load_classifier(),
        }

    def is_available(self) -> bool:
        """Check if at least embedding model is available."""
        if not self._embedding_loaded:
            self._load_embedding_model()
        return self._embedding_loaded

    def _get_topic_embedding(self, topic: str) -> np.ndarray:
        """Get or compute topic embedding (cached).

        Enriches topic name with description and keywords for better semantic matching.
        """
        if topic not in self._topic_cache:
            # Try to get topic description and keywords from config
            topic_text = topic
            try:
                import json
                config_path = "app/config/config.json"
                with open(config_path, 'r') as f:
                    config = json.load(f)

                for t in config.get('topics', []):
                    if t.get('name') == topic:
                        # Enrich topic text with description and keywords
                        parts = [topic]
                        if t.get('description'):
                            parts.append(t['description'])
                        if t.get('keywords'):
                            # Filter out exclusion keywords (starting with -)
                            keywords = [k for k in t['keywords'] if not k.startswith('-') and not k.startswith('company:') and not k.startswith('person:')]
                            if keywords:
                                parts.append(', '.join(keywords[:10]))  # Limit to 10 keywords
                        topic_text = '. '.join(parts)
                        logger.debug(f"Enriched topic embedding for '{topic}': {topic_text[:100]}...")
                        break
            except Exception as e:
                logger.debug(f"Could not enrich topic embedding: {e}")

            self._topic_cache[topic] = self.embedding_model.encode(topic_text, convert_to_numpy=True)
        return self._topic_cache[topic]

    def _compute_embedding_similarity(
        self,
        topic: str,
        title: str,
        summary: str,
        full_text: Optional[str] = None
    ) -> float:
        """
        Compute cosine similarity between topic and article.

        Uses full_text (truncated) when summary is short (<100 chars).
        """
        if not self._embedding_loaded:
            return 0.0

        # Get topic embedding (cached)
        topic_emb = self._get_topic_embedding(topic)

        # Compute article embedding
        # Use full_text fallback when summary is too short
        if full_text and len(summary or '') < 100:
            # Truncate full_text to ~1000 chars to stay within embedding limits
            truncated_text = full_text[:1000] if len(full_text) > 1000 else full_text
            article_text = f"{title}. {truncated_text}"
            logger.debug(f"Using truncated full_text for short summary ({len(summary or '')} chars)")
        else:
            article_text = f"{title}. {summary}"
        article_emb = self.embedding_model.encode(article_text, convert_to_numpy=True)

        # Cosine similarity
        similarity = np.dot(topic_emb, article_emb) / (
            np.linalg.norm(topic_emb) * np.linalg.norm(article_emb)
        )

        # Convert from [-1, 1] to [0, 1]
        score = (similarity + 1) / 2

        return float(score)

    def _compute_classifier_score(
        self,
        topic: str,
        title: str,
        summary: str
    ) -> Optional[float]:
        """
        Get relevance probability from fine-tuned classifier.
        """
        if not self._classifier_loaded:
            return None

        try:
            import torch

            # Format input like training data
            text = f"{topic} [SEP] {title}. {summary}"

            inputs = self.classifier_tokenizer(
                text,
                truncation=True,
                max_length=256,
                return_tensors="pt"
            )

            with torch.no_grad():
                outputs = self.classifier(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)
                # Return probability of "relevant" class (index 1)
                score = probs[0, 1].item()

            return score

        except Exception as e:
            logger.error(f"Classifier inference failed: {e}")
            return None

    def _compute_cross_encoder_score(
        self,
        topic: str,
        title: str,
        summary: str,
    ) -> Optional[float]:
        """Score (topic, title+summary) with the shared cross-encoder.

        Reuses the singleton loaded by ``app.retrieval.reranker`` — no
        duplicate model in memory. Returns ``None`` if the CE is unavailable
        so the caller degrades to the existing LLM fallback path.
        """
        try:
            from app.retrieval.reranker import score_pair
        except ImportError:
            logger.debug("Reranker module unavailable — skipping CE tier")
            return None
        document = f"{title}. {summary}".strip(". ")
        return score_pair(topic, document)

    def _compute_llm_score(
        self,
        topic: str,
        title: str,
        summary: str,
        use_local: bool = False,
        keywords: Optional[List[str]] = None,
    ) -> Optional[float]:
        """
        Get relevance score from LLM (most accurate, but slow/expensive).
        Used as fallback when other methods have low confidence.

        Args:
            topic: Topic to check relevance against
            title: Article title
            summary: Article summary
            use_local: If True, use local Qwen model instead of external GPT
            keywords: The monitor's actual keywords/entities. REQUIRED context for
                internal topic labels like "Brand Monitoring Wiley" — an article about
                John Wiley & Sons is not literally "about" the phrase 'Brand Monitoring
                Wiley', so judging against the bare label mis-scores real coverage.
        """
        # Internal monitor labels ("Brand Monitoring <X>") describe an entity watch,
        # not a subject — judge relevance against the entity + its keywords instead.
        brand_match = re.match(r'^Brand Monitoring\s+(.+)$', topic or '')
        entity = brand_match.group(1).strip() if brand_match else None
        kw_line = f"\nKey entities / search terms for this topic: {', '.join(keywords[:20])}" if keywords else ""
        if entity:
            # Brand-monitoring topics: BROAD relevance. The brand, its products, its named
            # competitors, and the industry/sector/policy it operates in all count as
            # relevant even when the brand is not named — this recovers sector coverage
            # (e.g. "academic publishing" news for a publisher watch) that a strict
            # "must be mainly about the entity" prompt wrongly drops. `keywords` carry the
            # brand / product / competitor context.
            prompt = f"""You are a relevance auditor for a brand monitor.

Brand/organization monitored: "{entity}"{kw_line}

Article Title: {title}
Article Summary: {summary}

Score 0.0-1.0 how relevant this article is to monitoring "{entity}":
- 0.7-1.0: primarily about {entity}, its products/services, its named competitors, or the industry/sector/policy it operates in.
- 0.3-0.6: {entity} or its sector is a notable part of a broader story.
- 0.0-0.2: only a coincidental name/keyword match about an unrelated subject (a different person, place or product of the same name), or unrelated local trivia.

Respond with ONLY a number between 0.0 and 1.0.

Score:"""
        else:
            # Theme topics keep the strict "must be primarily about the topic" auditor —
            # it works well for them and their trained classifier is reliable.
            materiality_rules = """
- MATERIALITY: the topic concerns developments of broad/strategic significance, NOT
  local administrative trivia. Purely LOCAL or single-institution items with no wider
  significance — e.g. one local college's admissions, exam results, fee notices, campus
  events, or municipal data — score LOW (0.1-0.3) even if on-topic. This is about the
  scope/materiality of the item, NOT the country it is reported from.
- Items of genuine global or strategic significance score normally regardless of where
  they occur or are reported — e.g. national R&D/science-funding policy, patent-cliff or
  generic-drug dynamics, major institutions, or developments affecting the field broadly."""
            prompt = f"""You are a strict relevance auditor. Rate the relevance of this article to the given topic.

Topic: {topic}{kw_line}

Article Title: {title}
Article Summary: {summary}

Rules:
- The article must be DIRECTLY about the topic, not just tangentially related
- Sharing a keyword is NOT enough — the article's main subject must match the topic
- Generic news that mentions a related term in passing scores 0.1-0.2
- Only score above 0.7 if the article is primarily about the topic{materiality_rules}

Respond with ONLY a number between 0.0 and 1.0.

Score:"""

        if use_local:
            return self._compute_local_llm_score(prompt)
        else:
            return self._compute_external_llm_score(prompt)

    def _compute_local_llm_score(self, prompt: str) -> Optional[float]:
        """Use local Qwen model (vLLM on port 8766) for relevance scoring."""
        try:
            from litellm import completion

            VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8765/v1")
            VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"

            response = completion(
                model=f"openai/{VLLM_MODEL}",
                api_base=VLLM_BASE_URL,
                messages=[
                    {"role": "system", "content": "You are a relevance scorer. Output only a number between 0.0 and 1.0."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.0,
            )

            response_text = response.choices[0].message.content.strip()
            # Extract first number from response
            match = re.search(r'(\d+\.?\d*)', response_text)
            if match:
                score = float(match.group(1))
                score = max(0.0, min(1.0, score))
                logger.info(f"🏠 Local Qwen relevance score: {score:.3f}")
                return score
            logger.warning(f"Could not parse local LLM score: {response_text}")
            return None

        except Exception as e:
            logger.error(f"Local LLM (Qwen) relevance scoring failed: {e}")
            return None

    def _compute_external_llm_score(self, prompt: str) -> Optional[float]:
        """Use external GPT model for relevance scoring."""
        try:
            from app.ai_models import AIModelFactory, extract_content

            # Highest-volume LLM path on the box (50k+ calls/day on wileytest).
            # Output is a single number, the exact task shape saas runs on
            # Nova Lite at scale — 13x cheaper than Haiku (cost directive
            # 2026-07-16: avoid Haiku unless necessary). Env knob for instant
            # revert: HYBRID_RELEVANCE_LLM_MODEL=gpt-5.4-mini. (Not
            # RELEVANCE_FALLBACK_MODEL — that's services/relevance_scorer.py's
            # outage-fallback knob and is pinned to bedrock-claude-haiku in
            # the tenant .envs.)
            ai = AIModelFactory.get_model(
                os.getenv("HYBRID_RELEVANCE_LLM_MODEL", "nova-lite")
            )
            response = ai.generate_sync(prompt, max_tokens=10, temperature=0.0)

            response_text = extract_content(response)
            # Extract the first number rather than strict float(): Bedrock
            # models often prefix text ("Score: 0.2"), and a parse failure
            # here becomes score None upstream — silently dropping the LLM
            # verdict. Mirrors _compute_local_llm_score.
            match = re.search(r'(\d+\.?\d*)', response_text)
            if not match:
                logger.warning(f"Could not parse external LLM score: {response_text!r}")
                return None
            score = float(match.group(1))
            score = max(0.0, min(1.0, score))
            logger.info(f"☁️ External GPT relevance score: {score:.3f}")
            return score

        except ValueError as e:
            logger.warning(f"Could not parse external LLM score: {e}")
            return None
        except Exception as e:
            logger.error(f"External LLM relevance scoring failed: {e}")
            return None

    def score_relevance(
        self,
        topic: str,
        title: str,
        summary: str,
        threshold: float = DEFAULT_THRESHOLD,
        use_llm_fallback: bool = True,
        force_llm: bool = False,
        use_local_llm: bool = False,
        full_text: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Score article relevance using hybrid approach.

        Args:
            topic: The topic to check relevance against
            title: Article title
            summary: Article summary
            threshold: Score threshold for binary relevance
            use_llm_fallback: Whether to use LLM for uncertain scores
            force_llm: Force LLM usage (for comparison/testing)
            use_local_llm: If True, use local Qwen instead of external GPT for fallback
            full_text: Optional full article text (used when summary is short)

        Returns:
            Dict with relevance decision and component scores
        """
        # Force LLM mode
        if force_llm:
            llm_score = self._compute_llm_score(topic, title, summary, use_local=use_local_llm, keywords=keywords)
            return {
                "topic": topic,
                "relevant": (llm_score or 0) >= threshold,
                "score": llm_score or 0,
                "embedding_score": None,
                "classifier_score": None,
                "ce_score": None,
                "llm_score": llm_score,
                "method": "llm_only",
                "confidence": "high" if llm_score is not None else "failed",
            }

        # Ensure models are loaded
        if not self._embedding_loaded:
            self._load_embedding_model()
        if not self._classifier_loaded:
            self._load_classifier()

        result = {
            "topic": topic,
            "relevant": False,
            "score": 0.0,
            "embedding_score": None,
            "classifier_score": None,
            "ce_score": None,
            "llm_score": None,
            "method": "none",
            "confidence": "low",
        }

        # Compute embedding similarity (always available if loaded)
        if self._embedding_loaded:
            embedding_score = self._compute_embedding_similarity(topic, title, summary, full_text)
            result["embedding_score"] = embedding_score
        else:
            embedding_score = None

        # Compute classifier score (if available).
        # The classifier was trained on "topic [SEP] title. summary" and collapses
        # to ~0 for EVERY article when the summary is missing: measured on ibaset's
        # 72-article brand corpus, title+summary scores 0.0001-0.9469 (AUC 0.981)
        # while title-only scores 0.0001-0.0034 (AUC 0.677) -- every article under
        # 0.005. Collection-time scoring often has no summary yet, so feed the
        # classifier the same text the embedding tier gets, and treat "no text to
        # judge" as unavailable rather than as a confident zero. Blending a
        # meaningless 0.0 at CLASSIFIER_WEIGHT dragged every score down by 60%.
        classifier_text = summary if (summary or "").strip() else (full_text or "")
        if self._classifier_loaded and classifier_text.strip():
            classifier_score = self._compute_classifier_score(topic, title, classifier_text)
            result["classifier_score"] = classifier_score
        else:
            classifier_score = None

        # Combine scores based on availability
        if classifier_score is not None and embedding_score is not None:
            # Both available - weighted combination
            combined_score = (
                CLASSIFIER_WEIGHT * classifier_score +
                EMBEDDING_WEIGHT * embedding_score
            )
            result["score"] = combined_score
            result["method"] = "hybrid"

        elif embedding_score is not None:
            # Only embedding available (new topic or classifier not loaded)
            result["score"] = embedding_score
            result["method"] = "embedding_only"

        elif classifier_score is not None:
            # Only classifier available
            result["score"] = classifier_score
            result["method"] = "classifier_only"

        # Set confidence based on score position
        # Only treat very low (<0.20) or very high (>0.85) as confident — everything
        # else gets LLM verification. The previous 0.35/0.65 window was too narrow;
        # the bimodal classifier (0.04 or 0.94) produced hybrid scores of ~0.24 or
        # ~0.82 that always landed outside the "uncertain" range, making LLM fallback
        # dead code.
        if result["score"] < 0.20 or result["score"] > 0.85:
            result["confidence"] = "high"
        else:
            result["confidence"] = "medium"

        # Don't let the cheap LLM override a CONFIDENT relevance classifier on trained
        # THEME topics: a 0.98-confident classifier being flipped down to 0.2 by the LLM
        # was dropping genuinely-relevant articles (e.g. Geopolitical coverage). When the
        # classifier is strongly positive we trust it and skip the LLM. Brand-monitoring
        # topics are EXEMPT — their classifier is unreliable on entity relevance (it
        # scores real brand coverage ~0.03), so the LLM remains the arbiter there.
        is_brand_topic = bool(re.match(r'^Brand Monitoring\s+', topic or ''))
        if not is_brand_topic and classifier_score is not None and classifier_score >= 0.90:
            result["confidence"] = "high"

        # Cross-encoder tier: for borderline cases, try the CE before paying
        # for an LLM call. Populates ce_score either way when enabled so we
        # can audit CE vs LLM agreement over time.
        # Theme topics only. Measured on real production documents
        # (title + summary, as scored below):
        #
        #   THEME topics  AUC 0.885  (199 relevant / 114 not)
        #   BRAND topics  AUC 0.478  (9 relevant / 86 not, hand-labelled)
        #
        # Brand relevance is entity disambiguation — SAGE Publishing vs Sage
        # Group plc vs sage the herb vs sage-agent-sdk on PyPI. That is a
        # named-entity problem, and a semantic reranker rates all of those as
        # similar, so on brand topics it performs at chance. Same underlying
        # reason the classifier-confidence guard above exempts brand topics.
        # NOTE: is_brand_topic above only recognises the "Brand Monitoring X"
        # naming. Tenants also carry "X - Brand Watch" topics (live, low
        # volume), which that predicate misses — so the CE gate uses its own,
        # covering both. Left the narrower one alone rather than silently
        # changing which topics the classifier-confidence guard applies to.
        is_brand_like = bool(_BRAND_TOPIC_RE.search(topic or ''))
        result["ce_score"] = None
        if USE_CE_TIER and result["confidence"] == "medium" and not is_brand_like:
            ce_score = self._compute_cross_encoder_score(topic, title, summary)
            if ce_score is not None:
                result["ce_score"] = ce_score
                # Accept-only: a CE below the bar means "no opinion", not
                # "reject", and falls through to the LLM. See the CE_HIGH note
                # at the top of this module for why the reject side is gone.
                if ce_score > CE_HIGH:
                    # Keep the hybrid score rather than adopting the CE's own
                    # value — the CE's scale is not comparable to the
                    # embedding/classifier scale, so writing it into `score`
                    # would corrupt the threshold comparison downstream.
                    result["score"] = max(result["score"], threshold)
                    result["method"] = f"{result['method']}+ce"
                    result["confidence"] = "high"
                    logger.info(
                        f"🎯 CE confirmed borderline case: ce={ce_score:.4f} "
                        f"(> {CE_HIGH}), skipping LLM"
                    )

        # LLM fallback for uncertain/borderline scores
        if use_llm_fallback and result["confidence"] != "high":
            fallback_type = "🏠 Local Qwen" if use_local_llm else "☁️ GPT"
            logger.info(f"🤖 {fallback_type} fallback triggered for borderline score {result['score']:.3f}")
            llm_score = self._compute_llm_score(topic, title, summary, use_local=use_local_llm, keywords=keywords)
            if llm_score is not None:
                result["llm_score"] = llm_score
                result["score"] = llm_score  # LLM overrides when uncertain
                result["method"] = f"{result['method']}+{'local_llm' if use_local_llm else 'llm'}_fallback"
                result["confidence"] = "high"

        # Make binary decision
        result["relevant"] = result["score"] >= threshold

        return result

    def score_batch(
        self,
        articles: List[Dict],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Score multiple articles efficiently.

        Args:
            articles: List of dicts with 'topic', 'title', 'summary'
            threshold: Score threshold

        Returns:
            List of result dicts
        """
        results = []

        # TODO: Batch embedding computation for efficiency
        for article in articles:
            result = self.score_relevance(
                topic=article.get("topic", ""),
                title=article.get("title", ""),
                summary=article.get("summary", ""),
                threshold=threshold,
            )
            results.append(result)

        return results

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "embedding_loaded": self._embedding_loaded,
            "classifier_loaded": self._classifier_loaded,
            "embedding_model": EMBEDDING_MODEL if self._embedding_loaded else None,
            "cached_topics": list(self._topic_cache.keys()),
            "classifier_weight": CLASSIFIER_WEIGHT,
            "embedding_weight": EMBEDDING_WEIGHT,
        }


# Singleton accessor
_service_instance = None


def get_hybrid_relevance_service() -> HybridRelevanceService:
    """Get the singleton hybrid relevance service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridRelevanceService()
    return _service_instance
