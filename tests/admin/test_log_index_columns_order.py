from pathlib import Path

def test_log_index_columns_are_last():
    html = Path("admin/templates/logs.html").read_text()
    head = html.split("<thead><tr>", 1)[1].split("</tr></thead>", 1)[0]
    assert head.index("<th>Result</th>") < head.index("<th>Session</th>")
    assert head.index("<th>Session</th>") < head.index("<th>Request</th>")
    assert head.index("<th>Request</th>") < head.index("<th>Trace</th>")
    assert head.index("<th>Trace</th>") < head.index("<th>Span</th>")

def test_log_row_index_cells_are_last():
    js = Path("admin/static/js/logs.js").read_text()
    row = js.split("tr.innerHTML=`", 1)[1].split("`;", 1)[0]
    assert row.index("${esc(x.result)}") < row.index("link('session_id'")
    assert row.index("link('session_id'") < row.index("link('request_id'")
    assert row.index("link('request_id'") < row.index("link('trace_id'")
    assert row.index("link('trace_id'") < row.index("link('span_id'")
