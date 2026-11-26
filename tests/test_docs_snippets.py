"""Every complete spec in the docs builds and verifies, so the docs can never rot.

Scans the fenced ```yaml blocks of `skills/**/*.md` and `README.md`:

* a block whose YAML is a mapping with `ninekit: 1` and `pieces` is a complete spec: it is built into a
  temporary folder, must report no slicing problems, and its manifest must verify;
* a block may name itself with a comment line `# file: <name>.yaml`; the named blocks of one markdown file
  are written side by side, so specs can `include:` each other;
* a block with `# theme for: <spec>.yaml` is a theme: that spec is built with it (`--theme`) and verified.

Blocks that are neither (fragments, a single layer) are documentation only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from ninekit.render import build
from ninekit.verify import verify_manifest

FENCE = re.compile(r"^```ya?ml[^\n]*\n(.*?)^```[ \t]*$", re.M | re.S)
FILE_TAG = re.compile(r"^#\s*file:\s*(\S+)\s*$", re.M)
THEME_TAG = re.compile(r"^#\s*theme for:\s*(\S+)\s*$", re.M)


def _doc_files() -> list[Path]:
    files = sorted((ROOT / "skills").glob("**/*.md"))
    readme = ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    return files


def _blocks(md: Path) -> list[dict]:
    """The yaml blocks of [md]: {line, text, data, name, theme_for}."""
    text = md.read_text(encoding="utf-8")
    out = []
    for m in FENCE.finditer(text):
        body = m.group(1)
        try:
            data = yaml.safe_load(body)
        except yaml.YAMLError as e:
            raise AssertionError(f"{md.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: invalid YAML: {e}")
        name = FILE_TAG.search(body)
        theme = THEME_TAG.search(body)
        out.append({"line": text.count("\n", 0, m.start()) + 1, "text": body, "data": data,
                    "name": name.group(1) if name else None, "theme_for": theme.group(1) if theme else None})
    return out


def _is_spec(data) -> bool:
    return isinstance(data, dict) and data.get("ninekit") == 1 and isinstance(data.get("pieces"), dict)


def _cases() -> list:
    cases = []
    for md in _doc_files():
        blocks = _blocks(md)
        for b in blocks:
            if _is_spec(b["data"]) or b["theme_for"]:
                rel = md.relative_to(ROOT).as_posix()
                cases.append(pytest.param(md, b, blocks, id=f"{rel}:{b['line']}"))
    return cases


CASES = _cases()


def test_docs_contain_specs():
    """The extraction found the docs' specs (guards against a fence regex that silently matches nothing)."""
    assert len(CASES) >= 10, [c.id for c in CASES]


@pytest.mark.parametrize("md, block, blocks", CASES)
def test_doc_snippet_builds_and_verifies(tmp_path, md, block, blocks):
    for b in blocks:                      # named blocks of the same document, side by side
        if b["name"]:
            target = tmp_path / b["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(b["text"], encoding="utf-8")
    if block["theme_for"]:
        spec_path = tmp_path / block["theme_for"]
        assert spec_path.exists(), f"theme for {block['theme_for']}: no block named that in {md.name}"
        theme_path = tmp_path / (block["name"] or "theme.yaml")
        if not block["name"]:
            theme_path.write_text(block["text"], encoding="utf-8")
    else:
        spec_path = tmp_path / (block["name"] or "spec.yaml")
        if not block["name"]:
            spec_path.write_text(block["text"], encoding="utf-8")
        theme_path = None
    out = tmp_path / "out"
    res = build(spec_path, theme=theme_path, out=out)
    assert not res.problems, res.problems
    report = verify_manifest(res.manifest_path)
    bad = [f.as_dict() for f in report.files if f.status != "ok"]
    assert report.ok, bad
