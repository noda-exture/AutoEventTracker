"""Offline checks executed by the bundled worker, not a system Python."""
import json
import os
from pathlib import Path
import subprocess
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from runtime_paths import data_directory, resource_path, recorder_command, tracker_command, child_process_options

HTML = b'''<style>#menu{width:200px}#choose{display:none}#menu:hover #choose{display:block}</style>
<div id="menu"><button id="trigger">Products</button><button id="choose"
onclick="fetch('/google-analytics.com/g/collect?en=select_product&tid=G-LOCALTEST')">Choose</button></div>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML if self.path == '/' else b'OK')

    def log_message(self, *_):
        pass


def run_self_test(output_path):
    result = {'ok': False, 'checks': []}
    output = Path(output_path)
    server = None
    try:
        from PySide6.QtWidgets import QApplication
        from main import AutoTrackerApp, copy_default_template, ensure_project_directories, load_stylesheet
        from global_settings import load_global_config
        from excel_reporter import generate_compare_report
        app = QApplication.instance() or QApplication([])
        load_stylesheet(app, str(resource_path('styles.qss')))
        window = AutoTrackerApp()
        window.show()
        app.processEvents()
        assert window.ui.tabs.tabText(0) == 'レポート生成'
        assert not window.ui.chk_compare.isChecked()
        assert app.styleSheet()
        assert window.ui.combo_proj.count() == 0, 'Fresh install contains projects'
        window.close()
        result['checks'].append('gui')
        assert load_global_config()['devices']
        project = data_directory() / 'project' / 'installer-smoke'
        ensure_project_directories(project)
        copy_default_template(project)
        result['checks'].append('new-project-and-template')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/'
        node_output = data_directory() / 'recorder-check.json'
        node = recorder_command()[0]
        subprocess.run([node, str(resource_path('recorder-smoke.cjs')), url, str(node_output)],
                       check=True, timeout=120, **child_process_options())
        assert len(json.loads(node_output.read_text())) == 2
        result['checks'].append('bundled-node-recorder-headed-and-headless')
        subprocess.run([node, '--require', str(resource_path('recorder-smoke-preload.cjs')),
                        str(resource_path('record.js')), 'installer-smoke', 'recorded', url,
                        'installer verification', '1280', '800'],
                       check=True, timeout=120, **child_process_options())
        recorded = json.loads((project / 'scenario' / 'recorded' / 'recorded.json').read_text(encoding='utf-8'))
        assert any(step['action'] == 'hover' for step in recorded['steps'])
        assert any(step['action'] == 'click' for step in recorded['steps'])
        result['checks'].append('recorder-saves-to-user-data')
        scenario = {
            'scenario_name': 'smoke', 'start_url': url,
            'execution_settings': {'max_retries': 1},
            'steps': [{'step_id': '0001', 'action': 'hover', 'selector': '#trigger'},
                      {'step_id': '0002', 'action': 'click', 'selector': '#choose'}],
        }
        (project / 'scenario' / 'smoke.json').write_text(json.dumps(scenario), encoding='utf-8')
        run = subprocess.run(tracker_command() + ['installer-smoke', 'smoke.json', '--headless'],
                             capture_output=True, text=True, encoding='utf-8', timeout=120,
                             **child_process_options())
        result['tracker_log'] = run.stdout + run.stderr
        assert run.returncode == 0, result['tracker_log']
        captures = list((project / 'scenario' / 'smoke').glob('smoke_*.json'))
        assert captures, 'Tracker did not save measurement data'
        events = json.loads(captures[0].read_text(encoding='utf-8'))['events']
        assert any(e.get('params', {}).get('en') == 'select_product' for e in events), events
        result['checks'].append('bundled-python-tracker-and-capture')
        report = generate_compare_report('installer-smoke', str(captures[0]), None, 'smoke.xlsx')
        assert report and Path(report).is_file()
        result['checks'].append('excel-report')
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if server:
            server.shutdown()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return 0 if result['ok'] else 1
