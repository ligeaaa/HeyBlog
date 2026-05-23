"""Build semantic embedding inputs for URL/title/text trainer models."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from typing import Any
from typing import TYPE_CHECKING

import numpy as np

from trainer.dataset.schema import SupervisedSample

if TYPE_CHECKING:
    import torch


BLOG_CLASSIFICATION_INSTRUCTION = (
    "Given a web page URL, title, and extracted visible text, classify whether the page is a personal "
    "or content blog rather than a company, product, documentation, portal, or utility page."
)


def clean_embedding_text(value: str) -> str:
    """Normalize whitespace while preserving the captured page text content."""

    return re.sub(r"\s+", " ", value).strip()


def build_embedding_query(sample: SupervisedSample, *, max_text_chars: int) -> str:
    """Format one sample as the query text passed into the embedding model."""

    text = clean_embedding_text(sample.text)
    if max_text_chars > 0:
        text = text[:max_text_chars]
    title = clean_embedding_text(sample.title)
    return "\n".join(
        [
            f"URL: {sample.normalized_url}",
            f"Domain: {sample.domain}",
            f"Title: {title}",
            f"Text: {text}",
        ]
    )


def build_detailed_instruct(task_description: str, query: str) -> str:
    """Wrap a query with the Qwen embedding instruction format."""

    return f"Instruct: {task_description}\nQuery: {query}"


def build_embedding_input_texts(
    samples: list[SupervisedSample],
    *,
    task_description: str = BLOG_CLASSIFICATION_INSTRUCTION,
    max_text_chars: int,
) -> list[str]:
    """Build Qwen-compatible embedding input strings for supervised samples."""

    return [
        build_detailed_instruct(
            task_description,
            build_embedding_query(sample, max_text_chars=max_text_chars),
        )
        for sample in samples
    ]


def last_token_pool(last_hidden_states: "torch.Tensor", attention_mask: "torch.Tensor") -> "torch.Tensor":
    """Pool the final non-padding token from transformer hidden states."""

    left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
    if left_padding:
        return last_hidden_states[:, -1]
    sequence_lengths = attention_mask.sum(dim=1) - 1
    batch_size = last_hidden_states.shape[0]
    return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]


class QwenEmbeddingEncoder:
    """Encode trainer samples with a Qwen embedding model."""

    def __init__(
        self,
        *,
        model_name: str,
        max_length: int,
        max_text_chars: int,
        batch_size: int,
        task_description: str = BLOG_CLASSIFICATION_INSTRUCTION,
        device: str | None = None,
    ) -> None:
        """Create a lazy encoder for Qwen embedding features.

        Args:
            model_name: Hugging Face model id or local path for the embedding model.
            max_length: Maximum tokenizer sequence length.
            max_text_chars: Maximum extracted page text characters included per sample.
            batch_size: Number of samples encoded in one forward pass.
            task_description: Instruction prepended to each query text.
            device: Optional torch device override such as "cpu" or "cuda".
        """

        self.model_name = model_name
        self.max_length = max_length
        self.max_text_chars = max_text_chars
        self.batch_size = max(batch_size, 1)
        self.task_description = task_description
        self.device = device
        self._tokenizer: Any | None = None
        self._model: Any | None = None

    def _load(self) -> tuple[Any, Any]:
        """Load tokenizer and model only when embeddings are first requested."""

        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

        import torch
        import torch.nn.functional as F  # noqa: F401  # Imported here to fail early with torch availability.
        from transformers import AutoModel
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(self.model_name, padding_side="left")
        model = AutoModel.from_pretrained(self.model_name)
        if self.device is not None:
            model = model.to(torch.device(self.device))
        model.eval()
        self._tokenizer = tokenizer
        self._model = model
        return tokenizer, model

    def __getstate__(self) -> dict[str, Any]:
        """Serialize encoder configuration without cached Hugging Face objects."""

        return {
            "model_name": self.model_name,
            "max_length": self.max_length,
            "max_text_chars": self.max_text_chars,
            "batch_size": self.batch_size,
            "task_description": self.task_description,
            "device": self.device,
            "_tokenizer": None,
            "_model": None,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore encoder configuration and keep model loading lazy."""

        self.model_name = state["model_name"]
        self.max_length = state["max_length"]
        self.max_text_chars = state["max_text_chars"]
        self.batch_size = state["batch_size"]
        self.task_description = state["task_description"]
        self.device = state["device"]
        self._tokenizer = None
        self._model = None

    def encode(self, samples: list[SupervisedSample]) -> np.ndarray[Any, Any]:
        """Return L2-normalized dense embeddings for the given samples."""

        if not samples:
            return np.empty((0, 0), dtype=np.float32)

        import torch
        import torch.nn.functional as F

        tokenizer, model = self._load()
        input_texts = build_embedding_input_texts(
            samples,
            task_description=self.task_description,
            max_text_chars=self.max_text_chars,
        )
        vectors: list[np.ndarray[Any, Any]] = []
        with torch.no_grad():
            for start in range(0, len(input_texts), self.batch_size):
                batch_texts = input_texts[start : start + self.batch_size]
                batch = tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                batch = batch.to(model.device)
                outputs = model(**batch)
                embeddings = last_token_pool(outputs.last_hidden_state, batch["attention_mask"])
                embeddings = F.normalize(embeddings, p=2, dim=1)
                vectors.append(embeddings.detach().cpu().numpy().astype(np.float32, copy=False))
        return np.vstack(vectors)

    def encode_with_progress(
        self,
        samples: list[SupervisedSample],
        *,
        progress: Callable[[str], None] | None = None,
    ) -> np.ndarray[Any, Any]:
        """Return embeddings and report batch progress for long generation jobs."""

        if not samples:
            return np.empty((0, 0), dtype=np.float32)

        import torch
        import torch.nn.functional as F

        emit = progress or (lambda message: print(message, file=sys.stderr, flush=True))
        emit(f"[embeddings] loading model={self.model_name}")
        tokenizer, model = self._load()
        input_texts = build_embedding_input_texts(
            samples,
            task_description=self.task_description,
            max_text_chars=self.max_text_chars,
        )
        total = len(input_texts)
        vectors: list[np.ndarray[Any, Any]] = []
        emit(f"[embeddings] encoding samples={total} batch_size={self.batch_size} max_length={self.max_length}")
        with torch.no_grad():
            for start in range(0, total, self.batch_size):
                end = min(start + self.batch_size, total)
                emit(f"[embeddings] batch {start + 1}-{end}/{total}")
                batch_texts = input_texts[start:end]
                batch = tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                batch = batch.to(model.device)
                outputs = model(**batch)
                embeddings = last_token_pool(outputs.last_hidden_state, batch["attention_mask"])
                embeddings = F.normalize(embeddings, p=2, dim=1)
                vectors.append(embeddings.detach().cpu().numpy().astype(np.float32, copy=False))
        emit("[embeddings] encoding complete")
        return np.vstack(vectors)
