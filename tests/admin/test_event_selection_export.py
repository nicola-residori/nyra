from pathlib import Path
R=Path(__file__).resolve().parents[2]
def test_event_selection_export():
 h=(R/"admin/templates/logs.html").read_text();j=(R/"admin/static/js/logs.js").read_text();assert "select-all-events" in h and "select-none-events" in h and "event-select" in j and "selectedEvents" in j and "exportItems" in j
