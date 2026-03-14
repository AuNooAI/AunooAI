#!/usr/bin/env python3
"""
Fine-tune a small LLM for policy classification using QLoRA.

Usage:
    # First, stop vLLM to free GPU memory
    sudo systemctl stop vllm  # or whatever the service is

    # Then train
    python scripts/train_policy_llm.py

    # Restart vLLM after training
    sudo systemctl start vllm

Requirements:
    pip install -r scripts/requirements_llm.txt
"""

import os
import json
import pandas as pd
import torch
from pathlib import Path
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"
OUTPUT_DIR = BASE_DIR / "models/policy_llm"

# Model choice - Mistral-7B-Instruct-v0.3 is excellent for instruction following
# Options: "mistralai/Mistral-7B-Instruct-v0.3", "Qwen/Qwen2.5-3B-Instruct", "microsoft/Phi-3-mini-4k-instruct"
MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.3"

# Category mapping
CATEGORY_COLUMNS = {
    "Violating Democratic Norms, Undermining Rule of Law": "undermining_democracy",
    "Hollowing State / Weakening Federal Institutions": "hollowing_state",
    "Suppressing Dissent / Weaponising State Against 'Enemies'": "suppressing_dissent",
    "Controlling Information Including Spreading Misinformation and Propaganda": "controlling_information",
    "Control of Science & Health to Align with State Ideology": "attacking_science",
    "Attacking Universities, Schools, Museums, Culture": "attacking_education",
    "Weakening Civil Rights": "weakening_civil_rights",
    "Corruption & Enrichment": "corruption",
    "Aggressive Foreign Policy & Global Destabilisation": "foreign_policy",
    "Anti-immigrant or Militarised Nationalism": "nationalism_immigration",
}

CATEGORY_NAMES = list(CATEGORY_COLUMNS.values())

# Category descriptions for the prompt
CATEGORY_DESCRIPTIONS = {
    "undermining_democracy": "Violations of democratic norms, rule of law, constitutional processes, judicial independence",
    "hollowing_state": "Dismantling federal agencies, mass firings, Schedule F, weakening institutions",
    "suppressing_dissent": "Using state power against opponents, protesters, activists, journalists, surveillance",
    "controlling_information": "Government misinformation, propaganda, press attacks, media censorship",
    "attacking_science": "Politicizing CDC/FDA/NIH/EPA, climate denial, vaccine misinformation",
    "attacking_education": "Targeting universities, DEI programs, curriculum changes, academic freedom",
    "weakening_civil_rights": "Rolling back LGBTQ+, reproductive rights, voting rights, racial equality",
    "corruption": "Conflicts of interest, nepotism, emoluments, self-dealing, questionable pardons",
    "foreign_policy": "NATO destabilization, trade wars, tariffs, aggressive foreign actions",
    "nationalism_immigration": "ICE raids, mass deportations, border enforcement, asylum restrictions",
}

# Training hyperparameters
MAX_LENGTH = 1024  # Room for longer inputs at inference
BATCH_SIZE = 4  # Small batch for memory efficiency
GRADIENT_ACCUMULATION = 4  # Effective batch size = 16
LEARNING_RATE = 1e-4  # Slightly lower for stability
NUM_EPOCHS = 6  # More epochs for better learning
LORA_R = 32  # Higher rank for more capacity
LORA_ALPHA = 64
LORA_DROPOUT = 0.05


def create_system_prompt():
    """Create the system prompt with category definitions."""
    categories_text = "\n".join([
        f"- {name}: {desc}"
        for name, desc in CATEGORY_DESCRIPTIONS.items()
    ])

    return f"""You are a policy classification expert analyzing Trump administration actions. Your task is to classify each article into ALL applicable policy categories. Most articles fit 2-4 categories.

CATEGORIES:
{categories_text}

IMPORTANT RULES:
1. Articles usually have MULTIPLE categories - don't be conservative
2. If an action undermines democratic norms, include "undermining_democracy"
3. If it involves propaganda or misinformation, include "controlling_information"
4. If it targets opponents or critics, include "suppressing_dissent"
5. If it affects civil liberties, include "weakening_civil_rights"

EXAMPLES:
- "Trump fires FBI director investigating his campaign" → corruption, undermining_democracy, suppressing_dissent
- "ICE raids target sanctuary cities" → nationalism_immigration, suppressing_dissent, weakening_civil_rights
- "White House spreads false claims about election fraud" → controlling_information, undermining_democracy

Respond with ONLY the applicable category names, separated by commas. Be thorough - include ALL categories that apply."""


def create_training_example(title: str, categories: list[str]) -> dict:
    """Create a training example in chat format."""
    system_prompt = create_system_prompt()

    if categories:
        response = ", ".join(sorted(categories))
    else:
        response = "none"

    # Format as chat messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Classify this article:\n\n{title}"},
        {"role": "assistant", "content": response}
    ]

    return {"messages": messages}


def load_and_prepare_data():
    """Load CSV and prepare training examples."""
    print(f"Loading data from {DATA_PATH}")

    df = pd.read_csv(DATA_PATH, skiprows=1)
    print(f"Loaded {len(df)} records")

    examples = []
    for _, row in df.iterrows():
        title = row.get("Title", "")
        if not title or pd.isna(title):
            continue

        # Get categories for this article
        categories = []
        for col, name in CATEGORY_COLUMNS.items():
            if row.get(col, "No") == "Yes":
                categories.append(name)

        example = create_training_example(title, categories)
        examples.append(example)

    print(f"Created {len(examples)} training examples")

    # Show distribution
    print("\nCategory distribution:")
    cat_counts = {name: 0 for name in CATEGORY_NAMES}
    for _, row in df.iterrows():
        for col, name in CATEGORY_COLUMNS.items():
            if row.get(col, "No") == "Yes":
                cat_counts[name] += 1

    for name, count in cat_counts.items():
        print(f"  {name}: {count} ({count/len(df)*100:.1f}%)")

    return examples


def format_chat_template(example, tokenizer):
    """Format example using the model's chat template."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False
    )
    return {"text": text}


def train():
    """Main training function."""
    print(f"Using model: {MODEL_NAME}")
    print(f"Output directory: {OUTPUT_DIR}")

    # Check GPU
    if not torch.cuda.is_available():
        print("ERROR: GPU required for QLoRA training")
        print("Make sure vLLM is stopped to free GPU memory")
        return

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # Free memory
    torch.cuda.empty_cache()

    # Load data
    examples = load_and_prepare_data()

    # QLoRA config - 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    print("\nLoading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load model with quantization
    print("Loading model with 4-bit quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # LoRA config - target all linear layers for better learning
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "lm_head"],
    )

    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Create dataset
    dataset = Dataset.from_list(examples)
    dataset = dataset.map(
        lambda x: format_chat_template(x, tokenizer),
        remove_columns=["messages"]
    )

    # Split dataset
    dataset = dataset.train_test_split(test_size=0.1, seed=42)

    print(f"\nDataset sizes: train={len(dataset['train'])}, test={len(dataset['test'])}")

    # Training arguments using SFTConfig
    training_args = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION,
        learning_rate=LEARNING_RATE,
        warmup_steps=100,
        weight_decay=0.01,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        report_to="none",
        max_grad_norm=0.3,
        max_length=MAX_LENGTH,
        dataset_text_field="text",
        packing=False,
    )

    # Initialize trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        processing_class=tokenizer,
    )

    # Train
    print("\n" + "=" * 50)
    print("Starting QLoRA training...")
    print("=" * 50)

    trainer.train()

    # Save the LoRA adapter
    print(f"\nSaving LoRA adapter to {OUTPUT_DIR / 'final'}")
    trainer.save_model(str(OUTPUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "final"))

    # Save config for inference
    config = {
        "base_model": MODEL_NAME,
        "categories": CATEGORY_NAMES,
        "category_descriptions": CATEGORY_DESCRIPTIONS,
        "system_prompt": create_system_prompt(),
        "lora_r": LORA_R,
        "lora_alpha": LORA_ALPHA,
    }

    with open(OUTPUT_DIR / "final" / "policy_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("\nTraining complete!")
    print(f"LoRA adapter saved to: {OUTPUT_DIR / 'final'}")
    print("\nTo use with vLLM, merge the adapter or load it separately.")

    return trainer


if __name__ == "__main__":
    train()
