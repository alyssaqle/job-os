import pytest


@pytest.fixture(autouse=True)
def _no_line_fill_by_default(monkeypatch):
    """The line-fill pass calls Claude; tests opt in explicitly by re-patching latex.short_lines."""
    from app import latex
    monkeypatch.setattr(latex, "short_lines", lambda pdf: [])
    monkeypatch.setattr(latex, "free_lines", lambda pdf: 0.0)
