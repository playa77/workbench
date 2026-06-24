import io
import re


class TextChunker:
    """Splits text into overlapping chunks using configurable strategies."""

    def chunk(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        strategy: str = "recursive",
    ) -> list[str]:
        if not text.strip():
            return []
        if strategy == "fixed":
            return self._fixed_chunk(text, chunk_size, chunk_overlap)
        if strategy == "sentence":
            return self._sentence_chunk(text, chunk_size, chunk_overlap)
        return self._recursive_chunk(text, chunk_size, chunk_overlap)

    def _fixed_chunk(self, text: str, size: int, overlap: int) -> list[str]:
        chunks: list[str] = []
        step = max(size - overlap, 1)
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end])
            start += step
        return chunks

    def _sentence_chunk(self, text: str, size: int, overlap: int) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return self._merge_fragments(sentences, size, overlap)

    def _recursive_chunk(self, text: str, size: int, overlap: int) -> list[str]:
        separators = ["\n\n", "\n", ". ", " "]
        for sep in separators:
            if sep in text:
                fragments = self._split_keep_separator(text, sep)
                return self._merge_fragments(fragments, size, overlap)
        return self._fixed_chunk(text, size, overlap)

    @staticmethod
    def _split_keep_separator(text: str, sep: str) -> list[str]:
        parts = text.split(sep)
        result: list[str] = []
        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                result.append(part + sep)
            elif part:
                result.append(part)
        return result

    @staticmethod
    def _merge_fragments(fragments: list[str], size: int, overlap: int) -> list[str]:
        chunks: list[str] = []
        for fragment in fragments:
            if not chunks or len(chunks[-1]) + len(fragment) > size:
                chunks.append(fragment)
            else:
                chunks[-1] += fragment
        overlapped: list[str] = []
        for chunk in chunks:
            if len(chunk) <= size:
                overlapped.append(chunk)
                continue
            step = max(size - overlap, 1)
            for start in range(0, len(chunk), step):
                overlapped.append(chunk[start:start + size])
        return overlapped


def extract_text_from_pdf(data: bytes) -> str:
    import fitz

    buf = io.BytesIO(data)
    doc = fitz.open(stream=buf, filetype="pdf")
    try:
        parts: list[str] = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)
    finally:
        doc.close()
