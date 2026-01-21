from app.ansible_analyzer import analyze_playbook_log

def test_analyzer_detects_failed():
    log = "TASK [something] **************************************************\nFAILED! => {"""
    results = analyze_playbook_log(log)
    assert results and any(r.get('advice') for r in results)

def test_analyzer_no_match():
    log = "All tasks completed successfully"
    results = analyze_playbook_log(log)
    assert len(results) == 1
    assert 'No clear pattern' in results[0]['advice']
