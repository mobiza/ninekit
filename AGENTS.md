# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Gemini CLI, Cursor, ...) working with or on
ninekit, an engine-agnostic generator of 9-slice UI sprites from YAML specs of vector layers.

## Making UI sprites with ninekit (any project)

Read and follow [skills/ninekit/SKILL.md](skills/ninekit/SKILL.md). It has the workflow, the hard rules
and pointers to the references:

* [workflow.md](skills/ninekit/references/workflow.md): reference screenshot → measured spec → verified
  sprites; side-by-side compare; checklist.
* [recipes.md](skills/ninekit/references/recipes.md): working specs for common looks.
* [spec.md](skills/ninekit/references/spec.md): the complete spec language and CLI.
* [engines.md](skills/ninekit/references/engines.md): export targets.
* [docs/DESIGN.md](docs/DESIGN.md): the design contract.

Run it with `ninekit ...` when installed, or `PYTHONPATH=src python3 -m ninekit ...` from this checkout.

Hard rules:

1. Never hand-edit or hand-paint a PNG: change the spec and rebuild.
2. Measure the reference (`ninekit measure`, `dp = px × design width / reference width`); don't eyeball it.
3. Layer back to front, outside in: outline → rings/bezel → walls/lip → face → gloss/highlights. Layers on
   the same outer edge thicken it: paint them `blend: atop`, or overflow and cut once with a piece `mask`.
4. Gradients are vertical only; anything horizontal lives inside the side slices. Let `slice: auto` and
   compaction slice; explicit `slice_px` only to reproduce legacy art. An axis that must not stretch is
   `stretch: fixed` (runtimes keep its natural length).
5. Pressable pieces are `outputs: [frame, face]`; labels go in `content`; shadows and glows in `overhang`.
6. `scales: [1, 2, 3]` by default for mobile; `mode: shade` for one art in many colours; noise/image
   fills need `stretch: tile`; other concepts are themes (`--theme`).
7. Done = `ninekit verify` passes, you opened and looked at the `ninekit preview` sheet, compared it
   with the reference (`ninekit compare`), exported, and checked it in the engine.

## Working on ninekit itself (contributors)

* Setup: `pip install -e ".[dev]"` (Python >= 3.10), or run everything with `PYTHONPATH=src`.
* Tests: `PYTHONPATH=src python3 -m pytest -q`. All must pass before you finish.
* **Golden fixtures must stay pixel-identical.** `tests/fixtures/gumdrop/` holds the Gumdrop sample art;
  `tests/test_gumdrop_golden.py` rebuilds `examples/gumdrop/` and compares every file pixel for pixel. Never
  regenerate or edit a fixture to make a test pass: regenerate (`NINEKIT_UPDATE_GOLDEN=1`) only for an
  intended change to the Gumdrop art, after looking at the previews. Never change the float operation order
  of `canvas.put` (normal blend), `sdf_rrect`/`sdf_circle`/`sdf_ellipse`, `vgrad` or `expr` evaluation:
  existing specs must rebuild bit for bit.
* `docs/DESIGN.md` is the contract between modules: if code and design disagree, change one of them
  deliberately, in the same change, never silently.
* Unknown keys are errors everywhere; errors are `NinekitError` with a message naming the field (printed
  as `error: ...`, exit 2).
* Every documented spec is built and verified by `tests/test_docs_snippets.py`: when you change the
  language, update `skills/ninekit/references/*.md` and keep that test green.
* Exporter/runtime changes are checked in the real engine: `demos/<engine>/regenerate.sh` regenerates the
  demo assets (they are git-ignored), then run the demo (see each script's header).
* The Claude Code plugin is `.claude-plugin/plugin.json` + `marketplace.json`; check them with
  `claude plugin validate .claude-plugin/plugin.json` and `claude plugin validate .`.
* Build outputs (`out/`, `*.preview.png`, `examples/**/export/`) are git-ignored; do not commit
  generated files outside `docs/images/` and `tests/fixtures/`.
