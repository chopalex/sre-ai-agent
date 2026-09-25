from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from .chunker import MarkdownHeaderChunker, DocumentChunk
from .vector_store import HybridVectorStore, SearchResult


class RAGContext(BaseModel):
    query: str
    results: List[SearchResult]
    formatted_context: str
    citations: List[str]


class RAGPipeline:
    """End-to-end RAG orchestrator for loading, indexing, and retrieval with citations."""

    def __init__(
        self,
        docs_dir: Path,
        top_k: int = 3,
        threshold: float = 0.15,
        chunker: Optional[MarkdownHeaderChunker] = None,
        store: Optional[HybridVectorStore] = None,
    ):
        self.docs_dir = Path(docs_dir)
        self.top_k = top_k
        self.threshold = threshold
        self.chunker = chunker or MarkdownHeaderChunker()
        self.store = store or HybridVectorStore()
        self.is_indexed = False

    def index(self, force_reload: bool = False):
        """Indexes all markdown runbooks in the docs directory."""
        if self.is_indexed and not force_reload:
            return

        self.store.clear()
        all_chunks: List[DocumentChunk] = []

        if not self.docs_dir.exists():
            self.docs_dir.mkdir(parents=True, exist_ok=True)

        for md_file in sorted(self.docs_dir.glob("*.md")):
            chunks = self.chunker.chunk_file(md_file)
            all_chunks.extend(chunks)

        self.store.add_chunks(all_chunks)
        self.is_indexed = True

    def query(self, query_text: str, top_k: Optional[int] = None) -> RAGContext:
        """Retrieves relevant documentation chunks and formats them with citations."""
        if not self.is_indexed:
            self.index()

        k = top_k or self.top_k
        results = self.store.search(query_text, top_k=k, threshold=self.threshold)

        citations = [r.citation for r in results]

        # Format context block with citations for LLM prompt
        formatted_blocks = []
        for r in results:
            header = f"--- [SOURCE CITATION: {r.citation} | Section: {r.chunk.section_title} | Score: {r.score}] ---"
            formatted_blocks.append(f"{header}\n{r.chunk.content}")

        context_str = "\n\n".join(formatted_blocks) if formatted_blocks else "No relevant runbooks found."

        return RAGContext(
            query=query_text,
            results=results,
            formatted_context=context_str,
            citations=citations,
        )
