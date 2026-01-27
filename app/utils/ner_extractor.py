"""NER Extractor Utility

Extracts named entities from text using spaCy for threat intelligence enrichment.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Lazy-load spaCy model
_nlp = None


def get_nlp():
    """Get or initialize the spaCy NLP model."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("Loaded spaCy model en_core_web_sm")
        except Exception as e:
            logger.error(f"Failed to load spaCy model: {e}")
            raise
    return _nlp


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract named entities from text using spaCy.

    Args:
        text: The text to extract entities from.

    Returns:
        Dictionary with entity types as keys and lists of entity values:
        - organizations: Companies, agencies, institutions (ORG)
        - locations: Countries, cities, states (GPE)
        - persons: People names (PERSON)
        - products: Software, malware names (PRODUCT)
    """
    if not text or not text.strip():
        return {
            'organizations': [],
            'locations': [],
            'persons': [],
            'products': [],
        }

    try:
        nlp = get_nlp()
        doc = nlp(text)

        entities = {
            'organizations': [],
            'locations': [],
            'persons': [],
            'products': [],
        }

        seen = set()
        for ent in doc.ents:
            # Normalize and deduplicate
            normalized = ent.text.strip()
            if not normalized:
                continue

            key = (ent.label_, normalized.lower())
            if key in seen:
                continue
            seen.add(key)

            if ent.label_ == 'ORG':
                entities['organizations'].append(normalized)
            elif ent.label_ == 'GPE':
                entities['locations'].append(normalized)
            elif ent.label_ == 'PERSON':
                entities['persons'].append(normalized)
            elif ent.label_ == 'PRODUCT':
                entities['products'].append(normalized)

        return entities

    except Exception as e:
        logger.warning(f"NER extraction failed: {e}")
        return {
            'organizations': [],
            'locations': [],
            'persons': [],
            'products': [],
        }


def extract_entities_batch(texts: List[str]) -> List[Dict[str, List[str]]]:
    """Extract named entities from multiple texts efficiently.

    Args:
        texts: List of texts to process.

    Returns:
        List of entity dictionaries, one per input text.
    """
    if not texts:
        return []

    try:
        nlp = get_nlp()
        results = []

        # Use pipe for efficient batch processing
        docs = nlp.pipe(texts, batch_size=50)

        for doc in docs:
            entities = {
                'organizations': [],
                'locations': [],
                'persons': [],
                'products': [],
            }

            seen = set()
            for ent in doc.ents:
                normalized = ent.text.strip()
                if not normalized:
                    continue

                key = (ent.label_, normalized.lower())
                if key in seen:
                    continue
                seen.add(key)

                if ent.label_ == 'ORG':
                    entities['organizations'].append(normalized)
                elif ent.label_ == 'GPE':
                    entities['locations'].append(normalized)
                elif ent.label_ == 'PERSON':
                    entities['persons'].append(normalized)
                elif ent.label_ == 'PRODUCT':
                    entities['products'].append(normalized)

            results.append(entities)

        return results

    except Exception as e:
        logger.warning(f"Batch NER extraction failed: {e}")
        return [{
            'organizations': [],
            'locations': [],
            'persons': [],
            'products': [],
        } for _ in texts]
