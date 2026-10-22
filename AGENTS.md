# cinetty

Run every command in this file from the directory that holds this file: the cinetty repository root. cinetty turns one `project.yaml` into an architecture animation that plays in the current terminal. Each template is a finished animation with a fixed layout, palette and rhythm, plus named fields. You fill the fields with the user's system; you never edit the layout. Everything you need is in this file and the files it names: `make templates`, each `template.yaml` and its example. You do not need to read the code in `cinetty/` or `scripts/`.

## Install

Run this once. It needs Python 3.12 or newer (or uv), Bash and Make on macOS or Linux.

```sh
make setup
```

`make setup` creates `.venv` and installs the light dependencies for the five text templates and checks for all examples. It does not install photo dependencies or download models. Everything stays inside this directory. If it stops, its last line names what is missing.

Both installation commands need network access. If the command fails because the network is blocked, ask the user to run the same command in their own terminal, then continue. Do not install the packages some other way, and do not use another project's Python environment.

## 1. Choose a template

```sh
make templates FORMAT=json
```

Each entry has `id`, `kind` (`video`), `terminal` (the size it needs), `duration`, `purpose`, a `preview` path and the path of a filled `example`. Pick the template whose purpose matches the shape of the user's system, not its subject. Decide by shape before you look at which facts you have, and keep that template; missing facts are handled in step 2, never by switching templates.

| Template | Fits a system that |
|---|---|
| `loop-landscape` | improves itself over rounds: propose, try candidates, keep what helped (wide) |
| `loop-portrait` | has a fast live loop on top and a slow learning loop below (tall) |
| `photo-loop` | reads real photos with a vision model while a background loop improves it |
| `pipeline` | plans work and has a router hand each step to one to three workers (agents, people or services), with an advisor that steps in |
| `screen-flow` | is an agent that operates a phone or another screen |
| `circuit-flow` | has about eight parts with signals running along wires (boards, services); the board always shows eight modules and sixteen wires |

If you chose `photo-loop`, install the photo dependencies and two local models before preparing or playing it:

```sh
make setup-photo
```

The shipped examples include source photos and detection results, but not the prepared outlines and animation images. Their first play also needs `make setup-photo`. Content checks with `make check` work with the light installation.

## 2. Write project.yaml

1. Read `templates/<id>/template.yaml`. Its `fields` section lists every field with its type, whether it is required, `max_cells`, item counts, number ranges and enum values. Its `notes` say what each part of the picture shows.
2. Read the example project named in `example`. It is a complete file that passes the check.
3. Read the user's repository. Write `project.yaml` where the user wants it:

   ```yaml
   template: <id>
   template_version: 1
   name: my-project
   fields:
     ...            # every field from template.yaml
   ```

   `pipeline`, `screen-flow` and `circuit-flow` also take `events:`, a list of timed steps, or the path of a `.jsonl` file with one event per line. Every event has `t` (seconds from the start, never decreasing) and `type`. The other keys depend on the type and are listed under `events` in `template.yaml`. The example shows a complete timeline.

Rules for the content:

- Fill fields from facts in the user's repository or from what the user told you. Do not present invented numbers or results as real.
- Every number on the screen comes from a field or an event of the project. The engine makes up none: a live loop shows the confidences you list, a counter changes only where an event gives a new value, and a number you leave out of an optional field is not shown (a status value shows `--`).
- When the user only names a system in a sentence and there is no repository to read, do not stop to ask. Design an illustrative architecture from that sentence: the parts, names and steps it implies. Keep the example's numbers (scores, confidences, counts, timings) as placeholders. In your reply, say that the picture is illustrative and list the fields that still hold the example's numbers.
- The photo template (`photo-loop`) uses the user's own photos. If the user has none, use the two sample photos in `assets/photos/` with the `blur` rectangles from the example, and say so in your reply. Preparing photos runs local models only.
- Widths are terminal cells. A CJK character counts as 2.
- Do not separate words with a spaced dot (` · ` or ` • `). Use a colon, a comma or another field.
- Text is shown literally. Braces are not variables, except where a field lists `placeholders` such as `{n}`.
- One `project.yaml` holds one language. For a second language, copy it and translate the text.
- File fields (photos) are paths relative to `project.yaml`. Use only photos the user may publish; blur faces and number plates with the `blur` field.
- A small `made with cinetty` appears at the bottom. Keep it unless the user asks to remove it; then add `credit: false` at the top level.

## 3. Check until it passes

```sh
make check INPUT=path/to/project.yaml FORMAT=json
```

The command exits non-zero when something is wrong and lists every problem with a `code`, the field `path` and a `hint`. A length problem also has `actual`, `limit` and `over`, and its hint names the exact change, for example `fix: shorten by 6 cells, to at most 34 cells`. The check also plays the whole animation and reports text that does not fit on screen, with the `time` and `round`.

Do what each hint says, then run the check again. Repeat until it prints no problems. Never work around a limit: do not add spaces, split a word over two fields or edit `template.yaml`.

## 4. Play it

```sh
make play INPUT="path/to/project.yaml"
```

The animation plays in the current terminal, which must be at least as large as the template's `terminal` size from step 1 (for example 120 x 40 cells). Ctrl-C stops it; `LOOP=1` repeats it. If the player asks for more cells, enlarge the terminal or reduce its font size. `make play` needs an interactive terminal. If your shell runs without one, it stops with a message; then ask the user to run the same command in their terminal. To see one moment as text, run `make once INPUT="path/to/project.yaml" AT=12`.

A video ends by itself after its `duration` and 6 more seconds on the last frame. The first play of `photo-loop` prepares the photos with local models, which can take several minutes; later plays reuse them.

- `photo-loop` needs a terminal that supports the Kitty graphics protocol (Ghostty, Kitty, WezTerm). The other five templates use text cells only.
- `screen-flow` plays the board alone.

To keep a video, record the terminal with the user's own screen recorder.

## Common problems

| Code | What to do |
|---|---|
| `too_long`, `too_long_on_screen` | Follow the hint: shorten the text at the path by the number of cells it names. When the hint names several fields, the total of the cuts must reach that number. |
| `too_many`, `too_few` | The template takes a fixed or limited number of items at that path. |
| `missing`, `empty`, `unknown_field` | Use exactly the fields in `template.yaml`; every required field needs a value. |
| `unknown_ref` | Use one of the names the hint lists; references must name an item that exists. |
| `out_of_range` | Use a value inside the range in the hint, or add the items it asks for. |
| `count_mismatch` | A count disagrees with the numbers it counts, for example `fallbacks` against `confidences` and the gate. Write the number the hint gives, or change the numbers or the gate. |
| `wrong_type` | Quote text that YAML would read as a number, a date or a mapping, for example `'roles: admin'`. |
| `time_goes_back`, `bad_time` | Event times are seconds from the start and never decrease. |
| `unknown_event` | Use the event types listed under `events` in `template.yaml`. |
| `spaced_dot` | Replace the spaced dot with a colon or a comma, or move the second part into another field. |
| `unsure_width` | Replace the symbol the hint names with another one, for example a symbol from the template's example. Terminals disagree on its width. |
| `no_split` | Write the text as `<before> → <after>`, for example `v1 → v3`. The comparison's divider runs through the arrow. |
| `cannot_draw` | Two fields disagree, for example a count larger than its list. Fix the round named in the path. |

## Changing a layout

Layouts live in `templates/<id>/scene.yaml` and are drawn by the engine in `cinetty/`. Edit them only when the user asks for a different layout; `docs/scene-reference.md` describes the format. Content never needs a layout change.
