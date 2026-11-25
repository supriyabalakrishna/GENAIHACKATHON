import pytest
from core.document_processor import LEGACY_ERROR

def test_legacy_rejection(tmp_path):
    path=tmp_path/"lesson.ppt"
    path.write_text("legacy")
    with pytest.raises(ValueError,match="Legacy"):
        from core.document_processor import extract_document
        extract_document(str(path))
