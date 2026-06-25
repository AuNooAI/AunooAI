# Policy Classifier Comparison Results

**Generated:** 2026-01-30 14:39:08

**Dataset:** trump-actions__1_.csv

## Summary Table

| Model | F1 Micro | F1 Macro | Exact Match | Precision | Recall |
|-------|----------|----------|-------------|-----------|--------|
| RoBERTa + DeBERTa (50/50) | 0.9558 | 0.9537 | 0.9000 | 0.9640 | 0.9477 |
| DeBERTa + LLM (70/30) | 0.9534 | 0.9508 | 0.8960 | 0.9552 | 0.9517 |
| DeBERTa-base | 0.9519 | 0.9494 | 0.8946 | 0.9553 | 0.9486 |
| RoBERTa-Large | 0.9252 | 0.9208 | 0.8194 | 0.9618 | 0.8913 |
| RoBERTa + LLM (70/30) | 0.9215 | 0.9175 | 0.8092 | 0.9493 | 0.8952 |
| Mistral-7B LLM | 0.6713 | 0.6953 | 0.2324 | 0.5798 | 0.7971 |

## Per-Category F1 Scores

| Category | RoBERTa + DeBER | DeBERTa + LLM ( | DeBERTa-base | RoBERTa-Large | RoBERTa + LLM ( | Mistral-7B LLM |
|----------|--------|--------|--------|--------|--------|--------|
| undermining_democracy | 0.940 | 0.937 | 0.932 | 0.891 | 0.887 | 0.580 |
| hollowing_state | 0.918 | 0.914 | 0.910 | 0.876 | 0.898 | 0.492 |
| suppressing_dissent | 0.958 | 0.955 | 0.955 | 0.947 | 0.939 | 0.683 |
| controlling_information | 0.938 | 0.933 | 0.934 | 0.877 | 0.874 | 0.581 |
| attacking_science | 0.978 | 0.975 | 0.976 | 0.967 | 0.971 | 0.896 |
| attacking_education | 0.954 | 0.952 | 0.955 | 0.927 | 0.914 | 0.798 |
| weakening_civil_rights | 0.946 | 0.945 | 0.948 | 0.870 | 0.883 | 0.548 |
| corruption | 0.957 | 0.947 | 0.941 | 0.928 | 0.903 | 0.771 |
| foreign_policy | 0.979 | 0.981 | 0.979 | 0.967 | 0.959 | 0.845 |
| nationalism_immigration | 0.970 | 0.970 | 0.964 | 0.959 | 0.947 | 0.761 |

## Analysis

**Best Overall:** RoBERTa + DeBERTa (50/50) (F1 Micro: 0.9558)

**Best Per Category:**
- undermining_democracy: RoBERTa + DeBERTa (50/50) (0.940)
- hollowing_state: RoBERTa + DeBERTa (50/50) (0.918)
- suppressing_dissent: RoBERTa + DeBERTa (50/50) (0.958)
- controlling_information: RoBERTa + DeBERTa (50/50) (0.938)
- attacking_science: RoBERTa + DeBERTa (50/50) (0.978)
- attacking_education: DeBERTa-base (0.955)
- weakening_civil_rights: DeBERTa-base (0.948)
- corruption: RoBERTa + DeBERTa (50/50) (0.957)
- foreign_policy: DeBERTa + LLM (70/30) (0.981)
- nationalism_immigration: DeBERTa + LLM (70/30) (0.970)

## Configuration Details

| # | Configuration | Description |
|---|---------------|-------------|
| 1 | RoBERTa-Large | RoBERTa-Large fine-tuned classifier |
| 2 | DeBERTa-base | DeBERTa-base fine-tuned classifier |
| 3 | RoBERTa + DeBERTa | SLM ensemble (50/50 weighted average) |
| 4 | DeBERTa + LLM | DeBERTa + Mistral-7B (70/30 weighted) |
| 5 | RoBERTa + LLM | RoBERTa + Mistral-7B (70/30 weighted) |
| 6 | Mistral-7B LLM | Mistral-7B with LoRA fine-tuning |

**Ensemble Strategy:**
- SLM + SLM: Average sigmoid scores, threshold at 0.5
- SLM + LLM: Weight SLM 70%, LLM 30% (LLM binary → 1.0/0.0)