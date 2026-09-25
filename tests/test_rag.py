from pathlib import Path
import pytest
from src.rag.chunker import MarkdownHeaderChunker
from src.rag.vector_store import HybridVectorStore
from src.rag.retriever import RAGPipeline


@pytest.fixture
def sample_docs_dir(tmp_path):
    doc1 = tmp_path / "runbook_disk.md"
    doc1.write_text(
        "# Runbook: Disk Full\n\n"
        "## Diagnostic Steps\n"
        "Run `df -h` to check available space on all partitions.\n"
        "Run `lsof +L1` to find unlinked files holding space.\n\n"
        "## Cleanup Protocol\n"
        "Clear rotated logs with `journalctl --vacuum-time=3d`.\n",
        encoding="utf-8",
    )

    doc2 = tmp_path / "runbook_nginx.md"
    doc2.write_text(
        "# Runbook: Nginx Troubleshooting\n\n"
        "## 502 Bad Gateway\n"
        "Check backend upstream socket and run `systemctl status nginx`.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_markdown_chunker(sample_docs_dir):
    chunker = MarkdownHeaderChunker()
    chunks = chunker.chunk_file(sample_docs_dir / "runbook_disk.md")

    assert len(chunks) >= 2
    # Check citation format
    first_chunk = chunks[0]
    assert first_chunk.source_file.endswith("runbook_disk.md")
    assert first_chunk.citation_tag.startswith("[runbook_disk.md#L")


def test_rag_retrieval_and_citations(sample_docs_dir):
    pipeline = RAGPipeline(docs_dir=sample_docs_dir, top_k=2)
    pipeline.index()

    # Query disk alert
    ctx = pipeline.query("диск переполнен df -h lsof")
    assert len(ctx.results) > 0
    assert any("runbook_disk.md" in c for c in ctx.citations)
    assert "[SOURCE CITATION:" in ctx.formatted_context

    # Query nginx 502
    ctx_nginx = pipeline.query("nginx 502 bad gateway upstream")
    assert len(ctx_nginx.results) > 0
    assert any("runbook_nginx.md" in c for c in ctx_nginx.citations)
