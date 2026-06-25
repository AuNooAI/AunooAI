#!/usr/bin/env python3
"""
Inference script for the fine-tuned Phi-3 policy classifier.

Usage:
    python scripts/policy_phi_inference.py "Trump fires inspector general"
    python scripts/policy_phi_inference.py --interactive
"""

import argparse
import json
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = BASE_DIR / "models/policy_phi/final"


class PolicyPhiClassifier:
    """Inference wrapper for the fine-tuned Phi-3 policy classifier."""

    def __init__(self, model_path: str = None, use_4bit: bool = True):
        self.model_path = Path(model_path) if model_path else MODEL_PATH

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                "Run train_policy_phi.py first."
            )

        # Load config
        with open(self.model_path / "policy_config.json") as f:
            self.config = json.load(f)

        self.base_model_name = self.config["base_model"]
        self.categories = set(self.config["categories"])
        self.system_prompt = self.config["system_prompt"]

        print(f"Loading Phi-3 model from {self.model_path}")
        print(f"Base model: {self.base_model_name}")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Load model
        if use_4bit and self.device == "cuda":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )
        else:
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                device_map="auto" if self.device == "cuda" else None,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            )

        # Load LoRA adapter
        self.model = PeftModel.from_pretrained(base_model, self.model_path)
        self.model.eval()

        print(f"Loaded {len(self.categories)} categories")

    def classify(self, title: str, summary: str = None, full_text: str = None) -> dict:
        """Classify an article."""
        # Build input
        input_parts = [f"Title: {title}"]
        if summary:
            input_parts.append(f"\nSummary: {summary}")
        if full_text:
            max_len = 2000
            if len(full_text) > max_len:
                full_text = full_text[:max_len] + "..."
            input_parts.append(f"\nFull text: {full_text}")

        input_text = "".join(input_parts)

        # Phi-3 chat format
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Classify this article:\n\n{input_text}"},
        ]

        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=100,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        response = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        # Parse categories
        predicted = []
        response_lower = response.lower()
        for cat in self.categories:
            if cat in response_lower:
                predicted.append(cat)

        return {
            "title": title[:100] + "..." if len(title) > 100 else title,
            "categories": predicted,
            "raw_response": response,
        }


def interactive_mode(classifier):
    """Interactive mode."""
    print("\nPhi-3 Policy Classifier")
    print("Enter article titles (Ctrl+C to exit)\n")

    while True:
        try:
            title = input("Article: ").strip()
            if not title:
                continue

            result = classifier.classify(title)
            print(f"\nCategories: {', '.join(result['categories']) or '(none)'}")
            print(f"Response: {result['raw_response']}\n")

        except KeyboardInterrupt:
            print("\nExiting")
            break


def main():
    parser = argparse.ArgumentParser(description="Phi-3 Policy Classifier")
    parser.add_argument("title", nargs="?", help="Article title")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--model-path", type=str)
    parser.add_argument("--cpu", action="store_true")

    args = parser.parse_args()

    classifier = PolicyPhiClassifier(args.model_path, use_4bit=not args.cpu)

    if args.interactive:
        interactive_mode(classifier)
    elif args.title:
        result = classifier.classify(args.title)
        print(f"\nTitle: {result['title']}")
        print(f"Categories: {', '.join(result['categories']) or '(none)'}")
        print(f"Response: {result['raw_response']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
