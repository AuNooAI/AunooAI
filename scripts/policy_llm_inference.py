#!/usr/bin/env python3
"""
Inference script for the fine-tuned policy classification LLM.

Usage:
    # Single article (title only)
    python scripts/policy_llm_inference.py "Trump fires inspector general"

    # With summary
    python scripts/policy_llm_inference.py "Trump fires inspector general" --summary "The president removed..."

    # Interactive mode
    python scripts/policy_llm_inference.py --interactive

    # Batch from database
    python scripts/policy_llm_inference.py --from-db --limit 100
"""

import argparse
import json
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = BASE_DIR / "models/policy_llm/final"


class PolicyLLMClassifier:
    """Inference wrapper for the fine-tuned policy LLM."""

    def __init__(self, model_path: str = None, use_4bit: bool = True):
        self.model_path = Path(model_path) if model_path else MODEL_PATH

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                "Run train_policy_llm.py first."
            )

        # Load config
        with open(self.model_path / "policy_config.json") as f:
            self.config = json.load(f)

        self.base_model_name = self.config["base_model"]
        self.categories = set(self.config["categories"])
        self.system_prompt = self.config["system_prompt"]

        print(f"Loading model from {self.model_path}")
        print(f"Base model: {self.base_model_name}")

        # Check device
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        if self.device == "cpu":
            print("WARNING: Running on CPU will be slow. GPU recommended.")
            use_4bit = False

        # Load tokenizer from base model (saved tokenizer may have issues)
        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
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
            if self.device == "cpu":
                base_model = base_model.to(self.device)

        # Load LoRA adapter
        self.model = PeftModel.from_pretrained(base_model, self.model_path)
        self.model.eval()

        print(f"Loaded {len(self.categories)} categories")

    def classify(self, title: str, summary: str = None, full_text: str = None) -> dict:
        """
        Classify an article.

        Args:
            title: Article title (required)
            summary: Article summary (optional, improves accuracy)
            full_text: Full article text (optional, improves accuracy further)

        Returns:
            dict with 'categories' and 'raw_response'
        """
        # Build input text
        input_parts = [f"Title: {title}"]
        if summary:
            input_parts.append(f"\nSummary: {summary}")
        if full_text:
            # Truncate full text to avoid context overflow
            max_text_len = 2000
            if len(full_text) > max_text_len:
                full_text = full_text[:max_text_len] + "..."
            input_parts.append(f"\nFull text: {full_text}")

        input_text = "".join(input_parts)

        # Format as chat
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Classify this article:\n\n{input_text}"},
        ]

        # Tokenize
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=100,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        # Decode response
        response = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        # Parse categories from response
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
    """Interactive classification mode."""
    print("\nInteractive Policy LLM Classifier")
    print("Enter article titles to classify (Ctrl+C to exit)")
    print("Optionally add summary after '|||' separator\n")

    while True:
        try:
            user_input = input("Article: ").strip()
            if not user_input:
                continue

            # Check for summary separator
            if "|||" in user_input:
                title, summary = user_input.split("|||", 1)
                title = title.strip()
                summary = summary.strip()
            else:
                title = user_input
                summary = None

            result = classifier.classify(title, summary)

            print(f"\nCategories: {', '.join(result['categories']) or '(none)'}")
            print(f"Raw response: {result['raw_response']}\n")

        except KeyboardInterrupt:
            print("\nExiting")
            break


def main():
    parser = argparse.ArgumentParser(description="Policy LLM Classifier Inference")
    parser.add_argument("title", nargs="?", help="Article title to classify")
    parser.add_argument("--summary", type=str, help="Article summary")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--model-path", type=str, help="Path to model directory")
    parser.add_argument("--cpu", action="store_true", help="Force CPU (slow)")

    args = parser.parse_args()

    use_4bit = not args.cpu

    classifier = PolicyLLMClassifier(args.model_path, use_4bit=use_4bit)

    if args.interactive:
        interactive_mode(classifier)
    elif args.title:
        result = classifier.classify(args.title, args.summary)
        print(f"\nTitle: {result['title']}")
        print(f"Categories: {', '.join(result['categories']) or '(none)'}")
        print(f"Raw response: {result['raw_response']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
