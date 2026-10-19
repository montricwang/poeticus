"""Qwen3-Reranker causal LM scorer for local offline Document RAG experiments.

IMPORTANT: use yes/no causal logits, NOT AutoModelForSequenceClassification:
the latter silently initializes a random score.weight with this model snapshot.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from backend.data_paths import MODELS_ROOT

MODEL_PATH = MODELS_ROOT / "Qwen3-Reranker-0.6B"


class Qwen3Reranker:
    def __init__(self, model_path: Path = MODEL_PATH, max_length: int = 512):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), local_files_only=True, padding_side="left"
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path), local_files_only=True, dtype=torch.float32
        ).eval()
        self.true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.false_id = self.tokenizer.convert_tokens_to_ids("no")
        if self.true_id == self.false_id or min(self.true_id, self.false_id) < 0:
            raise ValueError("模型 yes/no token ID 无效")
        self.prefix = self.tokenizer.encode(
            '<|im_start|>system\nJudge whether the Document meets the requirements '
            'based on the Query and the Instruct provided. '
            'Note that the answer can only be "yes" or "no".<|im_end|>\n'
            '<|im_start|>user\n', add_special_tokens=False
        )
        self.suffix = self.tokenizer.encode(
            '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n',
            add_special_tokens=False
        )
        self.max_length = max_length

    def score(self, question: str, passages: Sequence[str], batch_size: int = 2) -> list[float]:
        tokenizer = self.tokenizer
        instruction = "Given a web search query, retrieve relevant passages that answer the query"
        scores: list[float] = []
        with self.torch.inference_mode():
            for offset in range(0, len(passages), batch_size):
                prompts = [
                    f"<Instruct>: {instruction}\n<Query>: {question}\n<Document>: {passage}"
                    for passage in passages[offset:offset + batch_size]
                ]
                data = tokenizer(
                    prompts, padding=False, truncation="longest_first",
                    return_attention_mask=False,
                    max_length=self.max_length - len(self.prefix) - len(self.suffix),
                )
                ids = [self.prefix + row + self.suffix for row in data["input_ids"]]
                inputs = tokenizer.pad({"input_ids": ids}, padding=True, return_tensors="pt")
                logits = self.model(**inputs).logits[:, -1, :]
                odds = logits[:, self.true_id] - logits[:, self.false_id]
                scores.extend(float(x) for x in odds.float().tolist())
        return scores
