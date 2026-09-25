import math
import re
from typing import Dict, List, Set, Tuple
from pydantic import BaseModel
from .chunker import DocumentChunk


class SearchResult(BaseModel):
    chunk: DocumentChunk
    score: float
    citation: str


class HybridVectorStore:
    """Fast, zero-external-binary semantic vector store for Ops Runbooks.

    Combines BM25-scaled Term Frequency and Subword N-Gram Cosine Similarity.
    Delivers accurate retrieval across Russian/English technical vocabulary
    (e.g., 'диск', 'iowait', '502', 'df -h', 'nginx') without requiring 2GB models.
    """

    def __init__(self):
        self.chunks: List[DocumentChunk] = []
        self.doc_vectors: List[Dict[str, float]] = []
        self.idf: Dict[str, float] = {}

    def add_chunks(self, chunks: List[DocumentChunk]):
        """Indexes a collection of document chunks."""
        self.chunks.extend(chunks)
        self._rebuild_index()

    def clear(self):
        self.chunks.clear()
        self.doc_vectors.clear()
        self.idf.clear()

    def _tokenize(self, text: str) -> List[str]:
        """Extracts words and character 3-grams for robust matching."""
        # Clean and extract alphanumeric words
        words = re.findall(r"[a-zA-Zа-яА-Я0-9_-]{2,}", text.lower())
        tokens = list(words)

        # Add 3-grams for subword matching (e.g. 'iowait' -> 'iow', 'owa', 'wai', 'ait')
        for w in words:
            if len(w) >= 4:
                for i in range(len(w) - 2):
                    tokens.append(f"ng:{w[i:i+3]}")

        return tokens

    def _rebuild_index(self):
        """Computes IDF and doc TF-IDF vectors."""
        num_docs = len(self.chunks)
        if num_docs == 0:
            return

        doc_token_sets: List[Set[str]] = []
        doc_freqs: Dict[str, int] = {}

        # Count document frequencies
        for chunk in self.chunks:
            full_text = f"{chunk.section_title} {chunk.content}"
            tokens = set(self._tokenize(full_text))
            doc_token_sets.append(tokens)
            for t in tokens:
                doc_freqs[t] = doc_freqs.get(t, 0) + 1

        # Calculate IDF with smoothing
        self.idf = {
            t: math.log(1.0 + (num_docs - df + 0.5) / (df + 0.5))
            for t, df in doc_freqs.items()
        }

        # Build normalized TF-IDF vector for each document
        self.doc_vectors = []
        for idx, chunk in enumerate(self.chunks):
            full_text = f"{chunk.section_title} {chunk.section_title} {chunk.content}"
            tokens = self._tokenize(full_text)
            tf: Dict[str, float] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0.0) + 1.0

            vec: Dict[str, float] = {}
            for t, count in tf.items():
                if t in self.idf:
                    # BM25-like sublinear scaling
                    vec[t] = (1.0 + math.log(count)) * self.idf[t]

            # Normalize vector (L2 norm)
            norm = math.sqrt(sum(v * v for v in vec.values()))
            if norm > 0:
                vec = {k: v / norm for k, v in vec.items()}

            self.doc_vectors.append(vec)

    def search(self, query: str, top_k: int = 3, threshold: float = 0.15) -> List[SearchResult]:
        """Searches indexed documents and returns top-K ranked chunks."""
        query_tokens = self._tokenize(query)
        if not query_tokens or not self.doc_vectors:
            return []

        # Build query vector
        q_tf: Dict[str, float] = {}
        for t in query_tokens:
            q_tf[t] = q_tf.get(t, 0.0) + 1.0

        q_vec: Dict[str, float] = {}
        for t, count in q_tf.items():
            if t in self.idf:
                q_vec[t] = (1.0 + math.log(count)) * self.idf[t]

        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm == 0:
            return []
        q_vec = {k: v / q_norm for k, v in q_vec.items()}

        # Compute cosine similarity with each document
        scores: List[Tuple[int, float]] = []
        for idx, doc_vec in enumerate(self.doc_vectors):
            dot_product = sum(weight * doc_vec.get(term, 0.0) for term, weight in q_vec.items())
            if dot_product >= threshold:
                scores.append((idx, dot_product))

        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)

        results: List[SearchResult] = []
        for idx, score in scores[:top_k]:
            chunk = self.chunks[idx]
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=round(score, 4),
                    citation=chunk.citation_tag,
                )
            )

        return results
