# US Government Policy Classifier

A multi-label text classification model for categorizing news articles and government actions into policy categories. Trained on the [Trump Action Tracker](https://www.trumpactiontracker.info/) dataset.

## Overview

This classifier uses an ensemble of RoBERTa-Large and DeBERTa-base models to categorize political news and government actions into 10 policy categories. It achieves **F1 Micro: 0.9558** and **Exact Match: 90%** on the evaluation dataset.

## Dataset

Trained on ~2,259 labeled examples from the Trump Action Tracker:
- **Source**: https://www.trumpactiontracker.info/?start=2025-01-20&end=2026-01-30
- **Time Period**: January 20, 2025 - January 30, 2026
- **Format**: Multi-label classification (articles can belong to multiple categories)

The Trump Action Tracker is a comprehensive database cataloging actions taken by the Trump administration and their policy implications.

## Categories

The model classifies text into 10 policy categories:

| Category | Description |
|----------|-------------|
| `undermining_democracy` | Violations of democratic norms, rule of law, constitutional processes, attacks on judiciary |
| `hollowing_state` | Dismantling federal agencies, mass firings, DOGE, weakening government institutions |
| `suppressing_dissent` | Using state power against opponents, protesters, journalists, whistleblowers |
| `controlling_information` | Government misinformation, propaganda, media censorship, removing public data |
| `attacking_science` | Politicizing CDC/FDA/NIH/EPA, climate denial, vaccine misinformation |
| `attacking_education` | Targeting universities, DEI programs, curriculum changes, academic freedom |
| `weakening_civil_rights` | Rolling back LGBTQ+ rights, reproductive rights, voting rights protections |
| `corruption` | Conflicts of interest, nepotism, self-dealing, ethics violations |
| `foreign_policy` | NATO destabilization, trade wars, tariffs, aggressive foreign actions |
| `nationalism_immigration` | ICE raids, deportations, border enforcement, immigration restrictions |

## Model Performance

### Ensemble Comparison

| Model | F1 Micro | F1 Macro | Exact Match | Precision | Recall |
|-------|----------|----------|-------------|-----------|--------|
| **RoBERTa + DeBERTa (50/50)** | **0.9558** | **0.9537** | **90.0%** | 0.9640 | 0.9477 |
| DeBERTa-base | 0.9519 | 0.9494 | 89.5% | 0.9553 | 0.9486 |
| RoBERTa-Large | 0.9252 | 0.9208 | 81.9% | 0.9618 | 0.8913 |
| Mistral-7B LLM | 0.6713 | 0.6953 | 23.2% | 0.5798 | 0.7971 |

### Per-Category F1 Scores (Ensemble)

| Category | F1 Score |
|----------|----------|
| attacking_science | 0.978 |
| foreign_policy | 0.979 |
| nationalism_immigration | 0.970 |
| suppressing_dissent | 0.958 |
| corruption | 0.957 |
| attacking_education | 0.954 |
| weakening_civil_rights | 0.946 |
| undermining_democracy | 0.940 |
| controlling_information | 0.938 |
| hollowing_state | 0.918 |

## Usage

### Installation

```bash
pip install torch transformers
```

### Quick Start

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Load models
roberta_model = AutoModelForSequenceClassification.from_pretrained("aunoo/policy-classifier-roberta-large")
roberta_tokenizer = AutoTokenizer.from_pretrained("aunoo/policy-classifier-roberta-large")

deberta_model = AutoModelForSequenceClassification.from_pretrained("aunoo/policy-classifier-deberta-base")
deberta_tokenizer = AutoTokenizer.from_pretrained("aunoo/policy-classifier-deberta-base")

# Categories
CATEGORIES = [
    "undermining_democracy", "hollowing_state", "suppressing_dissent",
    "controlling_information", "attacking_science", "attacking_education",
    "weakening_civil_rights", "corruption", "foreign_policy", "nationalism_immigration"
]

def classify(text, threshold=0.5):
    """Classify text using ensemble."""
    # RoBERTa prediction
    inputs = roberta_tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        roberta_probs = torch.sigmoid(roberta_model(**inputs).logits)[0]

    # DeBERTa prediction
    inputs = deberta_tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        deberta_probs = torch.sigmoid(deberta_model(**inputs).logits)[0]

    # Ensemble (50/50 average)
    ensemble_probs = (roberta_probs + deberta_probs) / 2

    # Get categories above threshold
    predictions = [
        CATEGORIES[i] for i, prob in enumerate(ensemble_probs)
        if prob >= threshold
    ]

    return predictions, {cat: float(ensemble_probs[i]) for i, cat in enumerate(CATEGORIES)}

# Example
text = "Trump threatens tariffs on Denmark over Greenland purchase"
categories, scores = classify(text)
print(f"Categories: {categories}")
# Output: Categories: ['foreign_policy', 'nationalism_immigration']
```

### Using with Aunoo AI

The classifier is integrated into the [Aunoo AI](https://github.com/aunoo/aunoo-ai) policy tracker:

```python
from app.services.policy_classifier_service import get_classifier_service

classifier = get_classifier_service()
classifier.load_models()

result = classifier.classify("ICE conducts raids in sanctuary cities", return_scores=True)
print(result["categories"])  # ['nationalism_immigration', 'suppressing_dissent']
```

## Model Files

### HuggingFace Hub

- **RoBERTa-Large**: [aunoo/policy-classifier-roberta-large](https://huggingface.co/aunoo/policy-classifier-roberta-large)
- **DeBERTa-base**: [aunoo/policy-classifier-deberta-base](https://huggingface.co/aunoo/policy-classifier-deberta-base)

### Local Paths

```
models/policy_classifier/
├── final_roberta_large/     # RoBERTa-Large fine-tuned
│   ├── config.json
│   ├── model.safetensors
│   ├── tokenizer.json
│   └── ...
└── final/                   # DeBERTa-base fine-tuned
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── ...
```

## Training

### Requirements

```bash
pip install -r scripts/requirements_classifier.txt
```

### Train Models

```bash
# Train DeBERTa-base
python scripts/train_policy_classifier.py \
    --model microsoft/deberta-base \
    --output models/policy_classifier/final

# Train RoBERTa-Large
python scripts/train_policy_classifier.py \
    --model roberta-large \
    --output models/policy_classifier/final_roberta_large
```

### Evaluate

```bash
python scripts/evaluate_policy_classifier.py
```

### Compare All Configurations

```bash
python scripts/compare_all_classifiers.py
```

## Limitations

- **Domain-specific**: Trained specifically on US political news from the Trump administration era (2025-2026). May not generalize well to other political contexts, countries, or time periods.
- **English only**: The model is trained on English text only.
- **Multi-label**: Articles typically receive 2-4 category labels. Single-label classification may require threshold tuning.
- **Bias**: The training data reflects the editorial decisions of the Trump Action Tracker project.

## Citation

```bibtex
@misc{aunoo-policy-classifier,
  author = {Aunoo AI},
  title = {US Government Policy Classifier},
  year = {2026},
  publisher = {HuggingFace},
  howpublished = {\url{https://huggingface.co/aunoo/policy-classifier-roberta-large}},
  note = {Trained on Trump Action Tracker dataset}
}
```

## License

Apache 2.0

## Acknowledgments

- Training data from [Trump Action Tracker](https://www.trumpactiontracker.info/)
- Base models from HuggingFace: [RoBERTa-Large](https://huggingface.co/roberta-large), [DeBERTa-base](https://huggingface.co/microsoft/deberta-base)
