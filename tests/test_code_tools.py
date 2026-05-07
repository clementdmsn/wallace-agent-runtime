from __future__ import annotations

import sandbox
from tests.conftest import settings_for_sandbox
from tools import code_tools


PYTHON_SOURCE = '''
class Demo:
    def method(self, value):
        self.value = value
        return helper(value)


def helper(value):
    if value < 0:
        raise ValueError("negative")
    return value + 1


def duplicate():
    return 1


class Other:
    def duplicate(self):
        return 2


class Another:
    def duplicate(self):
        return 3
'''.strip()


def configure_sandbox(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    return settings


def test_code_tools_report_missing_files_and_directories(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'pkg').mkdir()

    assert code_tools.summarize_code_file('missing.py')['error'] == 'file does not exist'
    assert code_tools.list_code_symbols('pkg')['error'] == 'path is a directory'
    assert code_tools.explain_function_for_model('missing.py', 'helper')['error'] == 'file does not exist'


def test_summarize_and_list_code_symbols(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    source = tmp_path / 'demo.py'
    source.write_text(PYTHON_SOURCE, encoding='utf-8')

    summary = code_tools.summarize_code_file('demo.py')
    symbols = code_tools.list_code_symbols('demo.py')

    assert summary['status'] == 'ok'
    assert 'helper' in summary['content']
    assert symbols['status'] == 'ok'
    names = {item['name'] for item in symbols['symbols']}
    assert {'Demo', 'method', 'helper', 'duplicate', 'Other'} <= names


def test_explain_function_for_model_handles_exact_and_missing_symbols(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    source = tmp_path / 'demo.py'
    source.write_text(PYTHON_SOURCE, encoding='utf-8')

    helper = code_tools.explain_function_for_model('demo.py', 'helper')
    exact_duplicate = code_tools.explain_function_for_model('demo.py', 'Other.duplicate')
    missing = code_tools.explain_function_for_model('demo.py', 'missing')

    assert helper['status'] == 'ok'
    assert helper['content']['qualified_name'] == 'helper'
    assert 'exception_path' in helper['content']['effects']
    assert exact_duplicate['status'] == 'ok'
    assert exact_duplicate['content']['qualified_name'] == 'Other.duplicate'
    assert missing['status'] == 'error'
    assert missing['error'] == 'symbol not found'


def test_explain_function_for_model_reports_ambiguous_method_name(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'ambiguous.py').write_text(
        '''
class First:
    def duplicate(self):
        return 1


class Second:
    def duplicate(self):
        return 2
'''.strip(),
        encoding='utf-8',
    )

    ambiguous = code_tools.explain_function_for_model('ambiguous.py', 'duplicate')

    assert ambiguous['status'] == 'error'
    assert ambiguous['error'] == 'symbol is ambiguous'


def test_code_tools_return_syntax_errors(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'bad.py').write_text('def broken(:\n    pass\n', encoding='utf-8')

    symbols = code_tools.list_code_symbols('bad.py')
    explanation = code_tools.explain_function_for_model('bad.py', 'broken')

    assert symbols['status'] == 'error'
    assert 'python syntax error' in symbols['error']
    assert explanation['status'] == 'error'
    assert 'python syntax error' in explanation['error']
