from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_logs_ui_exports_filtered_records_and_correlated_request():
    html=(ROOT/"admin/templates/logs.html").read_text(); js=(ROOT/"admin/static/js/logs.js").read_text()
    assert 'id="export-json"' in html and 'id="export-csv"' in html
    assert "downloadRecords" in js and "Export request JSON" in js and "correlatedRecords" in js
def test_logs_ui_derives_stage_duration_for_started_completed_events():
    html=(ROOT/"admin/templates/logs.html").read_text(); js=(ROOT/"admin/static/js/logs.js").read_text()
    assert "<th>Stage</th>" in html and "<th>Duration</th>" in html
    assert "deriveStageDurations" in js and "stageName" in js and "durationMs" in js
