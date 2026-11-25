from pathlib import Path
from .chunker import clean_text, chunk_text

LEGACY_ERROR = "Legacy .ppt/.doc files are not supported. Please re-save as .pptx or .docx."
EMPTY_ERROR = "No extractable text found. OCR is not supported in this version."

def extract_document(path: str) -> tuple[list[dict], int | None]:
    suffix = Path(path).suffix.lower()
    if suffix in (".ppt", ".doc"):
        raise ValueError(LEGACY_ERROR)
    if suffix == ".pdf":
        import fitz
        doc = fitz.open(path)
        chunks = []
        for page_no in range(len(doc)):
            text = clean_text(doc[page_no].get_text())
            if text:
                chunks.extend(chunk_text(text, 0, "page", page_no + 1))
        return chunks, len(doc)
    if suffix == ".pptx":
        from pptx import Presentation
        prs = Presentation(path)
        chunks = []
        for slide_no, slide in enumerate(prs.slides, 1):
            parts = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    parts.append(shape.text)
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        parts.append(" | ".join(cell.text for cell in row.cells))
            if hasattr(slide, "notes_slide"):
                try:
                    note = slide.notes_slide.notes_text_frame.text
                    if note:
                        parts.append(note)
                except Exception:
                    pass
            text = clean_text("\n".join(parts))
            if text:
                chunks.extend(chunk_text(text, 0, "slide", slide_no))
        return chunks, len(prs.slides)
    if suffix == ".docx":
        from docx import Document
        doc = Document(path)
        parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                parts.append(paragraph.text)
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = clean_text("\n".join(parts))
        return chunk_text(text, 0, "none", None), None
    if suffix == ".txt":
        text = clean_text(Path(path).read_text(encoding="utf-8", errors="replace"))
        return chunk_text(text, 0, "none", None), None
    raise ValueError("Unsupported file format.")
