# Contributing to ninekit

Thanks for helping. Bug reports, new recipes, exporter fixes and docs are all welcome. This page covers the
development setup and the rules that keep ninekit's output stable. Coding agents: [AGENTS.md](AGENTS.md) holds the
same rules in a form written for you.

## Setup

Python 3.10 or newer.

```sh
git clone https://github.com/mobiza/ninekit
cd ninekit
pip install -e ".[dev]"            # numpy, pillow >= 10.1, pyyaml, pytest
```

Everything also runs from the checkout without installing: `PYTHONPATH=src python3 -m ninekit ...`.

## Tests

```sh
PYTHONPATH=src python3 -m pytest -q
```

All tests must pass before a change is done. Two of them deserve a word:

* **Golden fixtures.** `tests/test_gumdrop_golden.py` rebuilds `examples/gumdrop/` and compares every file with
  `tests/fixtures/gumdrop/` pixel for pixel. Never edit or regenerate a fixture to make a test pass. Regenerate
  only for an intended change to the Gumdrop art, after looking at the previews:

  ```sh
  NINEKIT_UPDATE_GOLDEN=1 PYTHONPATH=src python3 -m pytest -q tests/test_gumdrop_golden.py
  ```

* **Docs snippets.** `tests/test_docs_snippets.py` builds and verifies every complete spec (a YAML block with
  `ninekit: 1` and `pieces`) in `README.md` and `skills/**/*.md`. When you change the language, update
  `skills/ninekit/references/*.md` in the same change.

## Engine demos

Exporter and runtime changes are checked in the real engine. `demos/<engine>/` holds a small project per target;
its sprite assets are generated, not committed:

```sh
demos/godot/regenerate.sh            # GODOT=/path/to/Godot also imports it; then run the project (Godot 4.7)
demos/unity/regenerate.sh --check    # and runs the editor check in batch mode (Unity 6000.6)
demos/flutter/regenerate.sh          # then: cd demos/flutter && flutter test
demos/web/regenerate.sh              # then: python3 demos/web/check.py (CSS and Phaser in headless Chrome)
```

Each script's header says what it needs and how to run the check.

## README images

Every image the README shows is drawn from fresh ninekit builds by one script, which only lays sprites out and
labels them:

```sh
python3 docs/tools/make_readme_images.py              # all images into docs/images/
python3 docs/tools/make_readme_images.py hero neon    # some of them (--list shows the targets)
```

It uses macOS system fonts when present and falls back to Pillow's built-in font elsewhere. The README's
"A button in 20 lines" snippet must stay identical to `docs/tools/quick_piece.yaml` (the script warns if not).
Look at every image you regenerate before committing it. The engine screenshots (`docs/images/*_demo.png`) come
from the demos, for example `demos/unity/regenerate.sh --check` and `demos/web/check.py --docs`.

## Rules

* **Never hand-edit or hand-paint a PNG.** Change the spec and rebuild.
* **Existing specs must rebuild bit for bit.** Do not change the float operation order of `canvas.put` (normal
  blend), `sdf_rrect` / `sdf_circle` / `sdf_ellipse`, `vgrad` or expression evaluation.
* **[docs/DESIGN.md](docs/DESIGN.md) is the contract between the modules.** When code and design disagree, change
  one of them deliberately, in the same change, never silently.
* **Errors are precise.** Unknown keys are errors everywhere; raise `NinekitError` with a message that names the
  field (the CLI prints it as `error: ...` and exits 2).
* **Generated files stay out of git.** `out/`, `*.preview.png`, `examples/**/export/` and the demo assets are
  ignored; the only committed PNGs are under `docs/images/` and `tests/fixtures/`.
* **The Claude Code plugin** is `.claude-plugin/plugin.json` + `marketplace.json`; check them with
  `claude plugin validate .claude-plugin/plugin.json` and `claude plugin validate .`.

## Repository layout

```text
src/ninekit/                cli, spec, expr, sdf, paint, canvas, render, slicing, manifest, verify,
                            ninepatch (9-slice resampler), draw, preview, compare, measure, scaffold
src/ninekit/blocks/         code recipes (casual_button)
src/ninekit/exporters/      json, godot, unity, flutter, css, phaser
src/ninekit/adapters/       engine runtimes copied by `export --runtime`
examples/                   basics, gumdrop, neon, wood, recreate (their out/ is git-ignored)
demos/<engine>/             projects proving each export in the real engine
skills/ninekit/             the agent skill: SKILL.md + references/
.claude-plugin/             Claude Code plugin manifest + marketplace
docs/DESIGN.md              the design contract
docs/tools/                 the README image script
tests/                      pytest; fixtures under tests/fixtures/
```

## Pull requests

Keep a change focused, describe what you looked at (previews, engine runs), and add a line to
[CHANGELOG.md](CHANGELOG.md) for anything a user would notice. By contributing you agree that your work is released
under the [MIT License](LICENSE).
