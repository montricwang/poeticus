"""Mem0's HuggingFace adapter with Qwen3-specific query/document prompts.

Imported only when private user memory is explicitly enabled.
"""

from mem0.embeddings.huggingface import HuggingFaceEmbedding


class Qwen3RoleEmbedding(HuggingFaceEmbedding):
    """Use the same encoding roles as Poeticus document retrieval."""

    def _encode(self, texts: list[str], memory_action: str | None):
        role = "query" if memory_action == "search" else "document"
        vectors = self.model.encode(
            texts,
            prompt_name=role,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=4,
        )
        if vectors.shape[-1] != 1024:
            raise RuntimeError("Qwen3 embedding dimensions changed")
        return vectors.tolist()

    def embed(self, text: str, memory_action: str | None = None):
        return self._encode([text], memory_action)[0]

    def embed_batch(self, texts: list[str], memory_action: str = "add"):
        return self._encode(texts, memory_action) if texts else []
