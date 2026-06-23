"""
retriever.py
FAISS vector database retriever using FastEmbed for offline embeddings.

Embedder : fastembed TextEmbedding (ONNX, CPU-only, no sentence-transformers needed)
Index    : rag/index.faiss   — pre-built FAISS flat L2 index
Chunks   : rag/chunks.pkl    — list of text strings matching index rows
"""

import os
import warnings
import pickle

import faiss
import numpy as np

# Suppress ONNX runtime GPU-detection warnings (harmless on Pi — no GPU)
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["ORT_DISABLE_ALL_LOGS"] = "1"


class Retriever:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        index_path  = os.path.join(base_dir, "index.faiss")
        chunks_path = os.path.join(base_dir, "chunks.pkl")

        # Load FAISS index
        self.index = faiss.read_index(index_path)

        # Load text chunks
        with open(chunks_path, "rb") as f:
            self.chunks = pickle.load(f)

        # --- FastEmbed embedder (offline, CPU-safe, no internet needed) ---
        # Uses ONNX-quantised all-MiniLM-L6-v2 by default (~22 MB, already cached)
        from fastembed import TextEmbedding
        self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

        print(f"[RAG] Loaded {self.index.ntotal} vectors, {len(self.chunks)} chunks.")

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        """
        Embed the query and return the top-k matching text chunks.
        Returns an empty list on any error so callers stay safe.
        """
        try:
            # FastEmbed returns a generator — pull the first (and only) embedding
            query_vec = np.array(
                list(self.embedder.embed([query])), dtype=np.float32
            )  # shape (1, dim)

            scores, indices = self.index.search(query_vec, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if 0 <= idx < len(self.chunks):
                    results.append(self.chunks[idx])

            return results

        except Exception as e:
            print(f"[RAG] Retrieval error: {e}")
            return []
