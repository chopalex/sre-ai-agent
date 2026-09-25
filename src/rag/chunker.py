import re
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Represents a semantically coherent chunk of markdown documentation."""
    source_file: str
    section_title: str
    start_line: int
    end_line: int
    content: str
    metadata: dict = Field(default_factory=dict)

    @property
    def citation_tag(self) -> str:
        """Formatted citation tag (e.g. [runbook_disk_alert.md#L8-L15])."""
        filename = Path(self.source_file).name
        return f"[{filename}#L{self.start_line}-L{self.end_line}]"


class MarkdownHeaderChunker:
    """Splits markdown documents along header boundaries preserving context and lines."""

    def __init__(self, max_chunk_chars: int = 1200, min_chunk_chars: int = 60):
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars

    def chunk_file(self, file_path: Path) -> List[DocumentChunk]:
        """Reads and chunks a single markdown file."""
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return self.chunk_text(text, source_file=str(file_path))

    def chunk_text(self, text: str, source_file: str = "doc.md") -> List[DocumentChunk]:
        """Splits markdown text by headers and paragraphs."""
        lines = text.splitlines()
        chunks: List[DocumentChunk] = []

        current_header = "Introduction"
        current_lines: List[str] = []
        chunk_start_line = 1

        for idx, line in enumerate(lines, start=1):
            header_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())

            if header_match:
                # Flush existing chunk if it has content
                if current_lines:
                    chunk_content = "\n".join(current_lines).strip()
                    if len(chunk_content) >= self.min_chunk_chars:
                        chunks.append(
                            DocumentChunk(
                                source_file=source_file,
                                section_title=current_header,
                                start_line=chunk_start_line,
                                end_line=idx - 1,
                                content=chunk_content,
                            )
                        )
                    current_lines = []

                current_header = header_match.group(2).strip()
                chunk_start_line = idx
                current_lines.append(line)
            else:
                current_lines.append(line)

                # Split if section becomes too large
                total_len = sum(len(l) + 1 for l in current_lines)
                if total_len >= self.max_chunk_chars:
                    chunk_content = "\n".join(current_lines).strip()
                    chunks.append(
                        DocumentChunk(
                            source_file=source_file,
                            section_title=current_header,
                            start_line=chunk_start_line,
                            end_line=idx,
                            content=chunk_content,
                        )
                    )
                    current_lines = []
                    chunk_start_line = idx + 1

        # Flush remaining lines
        if current_lines:
            chunk_content = "\n".join(current_lines).strip()
            if len(chunk_content) >= self.min_chunk_chars or not chunks:
                chunks.append(
                    DocumentChunk(
                        source_file=source_file,
                        section_title=current_header,
                        start_line=chunk_start_line,
                        end_line=len(lines),
                        content=chunk_content,
                    )
                )

        return chunks
