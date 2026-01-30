#!/usr/bin/env python3
"""
Push trained policy classifier models to HuggingFace Hub for distribution.

Usage:
    # Login first
    huggingface-cli login

    # Push models (dry run)
    python scripts/push_models_to_hub.py --dry-run

    # Push models for real
    python scripts/push_models_to_hub.py

    # Push to custom organization
    python scripts/push_models_to_hub.py --org my-organization

Requirements:
    pip install huggingface_hub transformers
"""

import argparse
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# Model paths
MODELS = {
    "roberta": {
        "local_path": BASE_DIR / "models/policy_classifier/final_roberta_large",
        "hub_name": "policy-classifier-roberta-large",
        "description": "RoBERTa-Large fine-tuned for multi-label policy classification",
        "base_model": "roberta-large",
    },
    "deberta": {
        "local_path": BASE_DIR / "models/policy_classifier/final",
        "hub_name": "policy-classifier-deberta-base",
        "description": "DeBERTa-base fine-tuned for multi-label policy classification",
        "base_model": "microsoft/deberta-base",
    },
}

# Model card template
MODEL_CARD_TEMPLATE = """---
license: apache-2.0
language:
- en
tags:
- text-classification
- multi-label-classification
- policy-analysis
- news-classification
datasets:
- custom
base_model: {base_model}
metrics:
- f1
pipeline_tag: text-classification
---

# {title}

{description}

## Model Description

This model is a fine-tuned version of `{base_model}` for multi-label policy classification.
It categorizes news articles and political actions into 10 policy categories based on the
[Trump Action Tracker](https://trumpactiontracker.info) taxonomy.

## Categories

The model classifies text into the following 10 categories:

1. **undermining_democracy** - Violations of democratic norms, rule of law, constitutional processes
2. **hollowing_state** - Dismantling federal agencies, mass firings, weakening institutions
3. **suppressing_dissent** - Using state power against opponents, protesters, journalists
4. **controlling_information** - Government misinformation, propaganda, media censorship
5. **attacking_science** - Politicizing CDC/FDA/NIH/EPA, climate denial, vaccine misinformation
6. **attacking_education** - Targeting universities, DEI programs, curriculum changes
7. **weakening_civil_rights** - Rolling back LGBTQ+, reproductive rights, voting rights
8. **corruption** - Conflicts of interest, nepotism, self-dealing
9. **foreign_policy** - NATO destabilization, trade wars, aggressive foreign actions
10. **nationalism_immigration** - ICE raids, deportations, border enforcement

## Usage

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Load model
model_name = "{hub_id}"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)

# Classify
text = "Trump threatens tariffs on Denmark over Greenland"
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)

with torch.no_grad():
    outputs = model(**inputs)
    probs = torch.sigmoid(outputs.logits)[0]

# Get categories
categories = ["undermining_democracy", "hollowing_state", "suppressing_dissent",
              "controlling_information", "attacking_science", "attacking_education",
              "weakening_civil_rights", "corruption", "foreign_policy", "nationalism_immigration"]

threshold = 0.5
predicted = [cat for cat, prob in zip(categories, probs) if prob >= threshold]
print(predicted)  # ['foreign_policy', 'nationalism_immigration']
```

## Training Data

Trained on ~2,259 labeled examples from the Trump Action Tracker dataset,
which catalogs Trump administration actions and their policy implications.

## Performance

| Metric | Score |
|--------|-------|
| F1 Micro | {f1_micro:.4f} |
| F1 Macro | {f1_macro:.4f} |
| Exact Match | {exact_match:.2%} |

## Ensemble Usage

For best results, use this model as part of an ensemble with the complementary model:

- **RoBERTa-Large**: `{org}/policy-classifier-roberta-large`
- **DeBERTa-base**: `{org}/policy-classifier-deberta-base`

Ensemble (50/50 weighted average) achieves F1 Micro of 0.9558.

## Limitations

- Trained specifically on Trump administration political news
- May not generalize well to other political contexts or countries
- Multi-label classification means articles typically receive 2-4 categories

## License

Apache 2.0

## Citation

```bibtex
@misc{{aunoo-policy-classifier,
  author = {{Aunoo AI}},
  title = {{Policy Classifier for Political News Analysis}},
  year = {{2026}},
  publisher = {{HuggingFace}},
  url = {{https://huggingface.co/{hub_id}}}
}}
```
"""

# Performance metrics from evaluation
METRICS = {
    "roberta": {"f1_micro": 0.9252, "f1_macro": 0.9208, "exact_match": 0.8194},
    "deberta": {"f1_micro": 0.9519, "f1_macro": 0.9494, "exact_match": 0.8946},
}


def push_model(
    model_key: str,
    org: str,
    dry_run: bool = False,
    private: bool = False,
):
    """Push a single model to HuggingFace Hub."""
    from huggingface_hub import HfApi, create_repo
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    config = MODELS[model_key]
    metrics = METRICS[model_key]

    local_path = config["local_path"]
    hub_id = f"{org}/{config['hub_name']}"

    print(f"\n{'='*60}")
    print(f"Pushing {model_key} to {hub_id}")
    print(f"{'='*60}")

    if not local_path.exists():
        print(f"ERROR: Local model not found at {local_path}")
        return False

    if dry_run:
        print(f"[DRY RUN] Would push {local_path} to {hub_id}")
        print(f"  - Base model: {config['base_model']}")
        print(f"  - Description: {config['description']}")
        print(f"  - Metrics: F1={metrics['f1_micro']:.4f}")
        return True

    api = HfApi()

    # Create repo if needed
    try:
        create_repo(hub_id, repo_type="model", private=private, exist_ok=True)
        print(f"Repository {hub_id} ready")
    except Exception as e:
        print(f"Error creating repo: {e}")
        return False

    # Load model to verify it works
    print("Loading model to verify...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(local_path)
        model = AutoModelForSequenceClassification.from_pretrained(local_path)
    except Exception as e:
        print(f"Error loading model: {e}")
        return False

    # Create model card
    model_card = MODEL_CARD_TEMPLATE.format(
        title=config["hub_name"].replace("-", " ").title(),
        description=config["description"],
        base_model=config["base_model"],
        hub_id=hub_id,
        org=org,
        **metrics,
    )

    # Save model card
    readme_path = local_path / "README.md"
    with open(readme_path, "w") as f:
        f.write(model_card)
    print(f"Created model card at {readme_path}")

    # Push to Hub
    print(f"Pushing to {hub_id}...")
    try:
        model.push_to_hub(hub_id, private=private)
        tokenizer.push_to_hub(hub_id, private=private)

        # Upload additional files
        for extra_file in ["category_mapping.json", "config.json"]:
            file_path = local_path / extra_file
            if file_path.exists():
                api.upload_file(
                    path_or_fileobj=str(file_path),
                    path_in_repo=extra_file,
                    repo_id=hub_id,
                    repo_type="model",
                )
                print(f"  Uploaded {extra_file}")

        print(f"Successfully pushed to https://huggingface.co/{hub_id}")
        return True

    except Exception as e:
        print(f"Error pushing model: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Push policy classifier models to HuggingFace Hub")
    parser.add_argument("--org", type=str, default="aunoo", help="HuggingFace organization/username")
    parser.add_argument("--dry-run", action="store_true", help="Preview without pushing")
    parser.add_argument("--private", action="store_true", help="Create private repos")
    parser.add_argument("--model", choices=["roberta", "deberta", "both"], default="both",
                        help="Which model to push")

    args = parser.parse_args()

    if not args.dry_run:
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            user = api.whoami()
            print(f"Logged in as: {user['name']}")
        except Exception as e:
            print(f"Not logged in to HuggingFace Hub. Run: huggingface-cli login")
            print(f"Error: {e}")
            return

    models_to_push = ["roberta", "deberta"] if args.model == "both" else [args.model]

    results = {}
    for model_key in models_to_push:
        results[model_key] = push_model(
            model_key,
            org=args.org,
            dry_run=args.dry_run,
            private=args.private,
        )

    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    for model_key, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {model_key}: {status}")

    if all(results.values()):
        print("\nAll models pushed successfully!")
        print(f"\nUpdate app/services/policy_classifier_service.py with:")
        print(f'  HF_ROBERTA_MODEL = "{args.org}/policy-classifier-roberta-large"')
        print(f'  HF_DEBERTA_MODEL = "{args.org}/policy-classifier-deberta-base"')


if __name__ == "__main__":
    main()
