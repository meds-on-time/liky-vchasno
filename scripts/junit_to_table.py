"""SCRUM-39: turn a pytest JUnit XML report into a test log table for the report.

Usage:
    pytest --junitxml=reports/junit-unit.xml
    python scripts/junit_to_table.py reports/junit-unit.xml

Writes reports/junit-unit.md (Markdown) and reports/junit-unit.csv (CSV for Excel)
with columns: № | Тест | Що перевіряє | Результат | Дата.
"What it checks" is the test docstring; without one, the test name with
underscores replaced by spaces.
"""

import argparse
import ast
import csv
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ["№", "Тест", "Що перевіряє", "Результат", "Дата"]
RESULT_PASSED = "пройдено"
RESULT_FAILED = "не пройдено"
RESULT_ERROR = "помилка"
RESULT_SKIPPED = "пропущено"


@dataclass
class Row:
    number: int
    test: str
    checks: str
    result: str
    date: str


def _docstrings(module_file: Path) -> dict[str, str]:
    """Function name -> first line of its docstring."""
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node)
            if doc:
                out[node.name] = doc.strip().splitlines()[0].strip()
    return out


def _module_file(classname: str, root: Path) -> Path:
    """'tests.integration.test_api' -> <root>/tests/integration/test_api.py"""
    return root.joinpath(*classname.split(".")).with_suffix(".py")


def _result(case: ET.Element) -> str:
    if case.find("failure") is not None:
        return RESULT_FAILED
    if case.find("error") is not None:
        return RESULT_ERROR
    if case.find("skipped") is not None:
        return RESULT_SKIPPED
    return RESULT_PASSED


def _run_date(tree_root: ET.Element, xml_path: Path) -> str:
    suite = tree_root if tree_root.tag == "testsuite" else tree_root.find("testsuite")
    stamp = suite.get("timestamp") if suite is not None else None
    if stamp:
        try:
            return datetime.fromisoformat(stamp).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return datetime.fromtimestamp(xml_path.stat().st_mtime).strftime("%d.%m.%Y")


def read_rows(xml_path: Path, root: Path = ROOT) -> list[Row]:
    tree_root = ET.parse(xml_path).getroot()
    date = _run_date(tree_root, xml_path)
    docs_cache: dict[str, dict[str, str]] = {}
    rows = []
    for number, case in enumerate(tree_root.iter("testcase"), start=1):
        classname = case.get("classname", "")
        name = case.get("name", "")
        func, _, param = name.partition("[")
        if classname not in docs_cache:
            docs_cache[classname] = _docstrings(_module_file(classname, root))
        checks = docs_cache[classname].get(func) or func.removeprefix("test_").replace("_", " ")
        if param:
            checks = f"{checks} [{param.rstrip(']')}]"
        module = classname.rsplit(".", 1)[-1]
        rows.append(Row(number, f"{module}::{name}", checks, _result(case), date))
    return rows


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|")


def to_markdown(rows: list[Row], title: str) -> str:
    passed = sum(r.result == RESULT_PASSED for r in rows)
    failed = sum(r.result in (RESULT_FAILED, RESULT_ERROR) for r in rows)
    skipped = sum(r.result == RESULT_SKIPPED for r in rows)
    summary = (
        f"Усього тестів: {len(rows)}, пройдено: {passed}, "
        f"не пройдено або з помилкою: {failed}, пропущено: {skipped}."
    )
    lines = [
        f"# {title}",
        "",
        summary,
        "",
        "| " + " | ".join(HEADER) + " |",
        "|" + "|".join("---" for _ in HEADER) + "|",
    ]
    for r in rows:
        cells = [str(r.number), f"`{r.test}`", r.checks, r.result, r.date]
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"


def write_csv(rows: list[Row], path: Path) -> None:
    # utf-8-sig so Excel opens Cyrillic correctly
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(HEADER)
        for r in rows:
            writer.writerow([r.number, r.test, r.checks, r.result, r.date])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("xml", type=Path, help="JUnit XML from pytest --junitxml")
    parser.add_argument("--title", default="Журнал результатів тестування")
    args = parser.parse_args(argv)

    rows = read_rows(args.xml, ROOT)
    md_path = args.xml.with_suffix(".md")
    csv_path = args.xml.with_suffix(".csv")
    md_path.write_text(to_markdown(rows, args.title), encoding="utf-8")
    write_csv(rows, csv_path)
    print(f"{len(rows)} tests -> {md_path}, {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
