from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_logs_ui_exposes_pipeline_fields():
    html=(ROOT/"admin/templates/logs.html").read_text(); js=(ROOT/"admin/static/js/logs.js").read_text()
    assert "<th>Operation</th>" in html
    assert "pipelineLabel" in js
    assert "Identity" in js and "LLM" in js and "Skills" in js
