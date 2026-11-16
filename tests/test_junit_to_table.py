"""SCRUM-39: the script that turns JUnit XML into the test log table."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "junit_to_table", ROOT / "scripts" / "junit_to_table.py"
)
junit_to_table = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(junit_to_table)

XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" timestamp="2026-11-16T10:00:00.000000+02:00">
<testcase classname="tests.test_sample" name="test_with_doc" time="0.01"/>
<testcase classname="tests.test_sample" name="test_no_doc_here" time="0.01">
<failure message="boom">assert 1 == 2</failure></testcase>
<testcase classname="tests.test_sample" name="test_param[a|b]" time="0.01">
<skipped message="no db"/></testcase>
</testsuite></testsuites>
"""

SOURCE = '''
def test_with_doc():
    """Перевіряє щось важливе"""


def test_no_doc_here():
    pass


def test_param(x):
    """Параметризований тест"""
'''


def make_files(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(SOURCE, encoding="utf-8")
    xml = tmp_path / "junit.xml"
    xml.write_text(XML, encoding="utf-8")
    return xml


def test_rows_take_docstring_name_result_and_date(tmp_path):
    """Скрипт журналу: опис з docstring, без нього – з назви; результат і дата запуску"""
    rows = junit_to_table.read_rows(make_files(tmp_path), root=tmp_path)
    assert [(r.number, r.test, r.checks, r.result, r.date) for r in rows] == [
        (1, "test_sample::test_with_doc", "Перевіряє щось важливе", "пройдено", "16.11.2026"),
        (2, "test_sample::test_no_doc_here", "no doc here", "не пройдено", "16.11.2026"),
        (3, "test_sample::test_param[a|b]", "Параметризований тест [a|b]", "пропущено",
         "16.11.2026"),
    ]


def test_main_writes_markdown_and_csv(tmp_path, monkeypatch):
    """Скрипт журналу створює таблиці Markdown і CSV з колонками № | Тест | Що перевіряє"""
    xml = make_files(tmp_path)
    monkeypatch.setattr(junit_to_table, "ROOT", tmp_path)
    assert junit_to_table.main([str(xml)]) == 0
    md = xml.with_suffix(".md").read_text(encoding="utf-8")
    assert "| № | Тест | Що перевіряє | Результат | Дата |" in md
    assert "Усього тестів: 3, пройдено: 1" in md
    assert "test_param[a\\|b]" in md  # pipe escaped in Markdown
    csv_text = xml.with_suffix(".csv").read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0] == "№;Тест;Що перевіряє;Результат;Дата"
