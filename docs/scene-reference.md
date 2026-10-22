# Scene and template file reference

This page describes the three files of a cinetty template and the project file that fills it. Read it when you change a layout. To make a video with an existing layout you only write a project file; see `AGENTS.md`.

| File | Who writes it | What it holds |
|---|---|---|
| `templates/<id>/template.yaml` | template author | id, version, purpose, output, the fields a project fills (with types and limits), the event types, the example projects |
| `templates/<id>/scene.yaml` | template author | the fixed layout and motion, with `{{field.path}}` references to the project's fields |
| `templates/<id>/preview/` | template author | `still.png` and `clip.mp4` of the example |
| `project.yaml` | user or the user's agent | `template`, `template_version`, `name`, `fields`, and `events` for event templates |

Coordinates are terminal cells, origin at the top left, rectangles `[x0, y0, x1, y1]` inclusive. Widths are measured in cells: a CJK character takes two. Colors are a palette name, `[r, g, b]`, or `[mix, a, b, k]` (color `a` moved a share `k` towards `b`).

## project.yaml

```yaml
template: circuit-flow        # template id (make templates)
template_version: 1           # must match template.yaml's version
name: my-board                # output file name, without extension
credit: true                  # optional; false hides the small "made with cinetty" line
fields: {...}                 # every field in template.yaml
events: [...]                 # event templates only: a list, or the path of a .jsonl file
```

`credit` defaults to `true`: every template draws a small `made with cinetty` in its dimmest status colour at the bottom right, on the lowest free row, and only where the cells are empty. It is not a field, so it never counts toward a width limit. Set `credit: false` to leave it out; any other value than `true` or `false` is a `wrong_type` error.

Unknown top-level keys and unknown fields are errors. File fields (photos, results, clips) are paths relative to the project file. Text is literal: braces in field values are never read as bindings.

## template.yaml

| Key | Meaning |
|---|---|
| `id`, `version` | template id and its version; projects name both |
| `title`, `purpose` | name and a one-line purpose, shown by `make templates` |
| `kind` | `video` or `still` |
| `output`, `duration` | output size and frame rate, length; for listing only |
| `preview` | `{still, clip}` paths relative to the template directory |
| `example` | `{en: path, zh: path}` example projects, relative to the repository root |
| `notes` | what the layout is, for the person or agent filling it |
| `fields` | the field tree (below) |
| `events` | event templates: `desc` and `types` (type name to a description of its keys); the board checks events itself |

Field types:

| `type` | Keys | Checked |
|---|---|---|
| `text` | `max_cells`, `allowed_chars`, `placeholders` (names allowed in `{…}`, measured with `measure` values), `allow_empty`, `split_at` (a symbol that must join exactly two parts, with a space on each side) | width in cells, control characters, characters outside `allowed_chars`, a missing `split_at` symbol |
| `number`, `integer` | `range: [lo, hi]`, `unit`, `count_of: list.path` | type and range; with `count_of`, at most the number of items in that list |
| `enum` | `values` | value is listed |
| `ref` | `to: list.path` or `to: list[].key` | value names an item of that list |
| `list` | `items` (exact count), or `min_items`, `max_items`; `of` (item schema) | count, then each item |
| `record` | `fields` | each field; unknown keys are errors |
| `file` | `formats` (extensions) | file exists relative to the project file |
| `any` | none | nothing |

Every field takes `desc` and `required` (default `true`). An optional field can list `needs: [other, ...]`: fields of the same record that must be present when it is set.

## scene.yaml: round driver

The round driver plays an intro, N rounds of the same phases, an all-lit hold, a freeze and an outro that fades back to the opening frame, so the video loops. It is the default driver.

### Top-level keys

| Key | Meaning |
|---|---|
| `canvas` | `{cols, rows, fps}` |
| `palette` | extra or changed colors by name; the base names are `bg dim gray soft white bright line red track gold` |
| `style` | `flash` (seconds a box flashes after a packet arrives), `title_margin`, `core_pulse: {wires, decay}`, `periodic_first`, `finale_pulses: {count, every, dur}` |
| `title` | `{text, row, scatter, hue_speed}`: rainbow title, letters spread over `scatter` columns at the start and end |
| `data` | values shared by all rounds, read as `data.<key>` |
| `rounds` | list of per-round values, read as `round.<key>`; usually `"{{rounds}}"` |
| `derive` | `{key: binding}` computed once per round and added to `round` |
| `counters` | `{name: {key, phase, span}}`: a number that rolls from `round.<key>[0]` to `[1]` during `phase` |
| `version` | `{key, phase, at}`: the adopted version switches during `phase` when the round has a winner |
| `ticker` | a fast inner loop (see [ticker](#ticker)) |
| `photo_layer` | photos shown through the Kitty graphics protocol (see [photo layer](#photo-layer)) |
| `timeline` | phases and timing (below) |
| `boxes` | boxes and their content |
| `wires` | connecting lines and the packets that run along them |
| `overlay` | components drawn on the whole screen (status line, dividers, labels) |

### timeline

| Key | Meaning |
|---|---|
| `intro` | seconds before round 1 |
| `phases` | list of `{name, dur, kind, skip_last}`; `kind` is a free word used by `duration_scale`; `skip_last` drops the phase in the last round |
| `duration_scale` | per round, `{kind: factor}`; `0.7` means the phase takes 70% of its listed duration |
| `hold`, `freeze`, `outro` | seconds of the all-lit hold, the freeze and the fade back to the opening |
| `snapshot` | `{round, phase, at}`: the frame shown during the freeze and the fade |

### boxes

| Key | Meaning |
|---|---|
| `id`, `rect`, `color`, `title` | identity, rectangle, border color, title cut into the top border |
| `style` | `normal`, `frame` (a section frame) or `core` (double border, rotating ring, pulse) |
| `layer` | `round` (follows the round timeline and the freeze) or `live` (always real time) |
| `lit` | phases that light the box: a name, or `{phase, level}` |
| `lit_windows` | `[[from, to], …]` extra lit windows, as a share of the round |
| `lit_tick` | light the box on ticker steps |
| `idle`, `level`, `snapshot` | brightness when idle, a fixed brightness, brightness during the freeze |
| `core` | settings of a `core` box |
| `content` | list of components |

### Components

Each component is `{type, …}`. Shared keys: `row` (line inside the box), `x` (column from the left border), `color`, `bold`, `z` (`over` or `top`), `show: {phase, at}` (hidden until that point of the round), `field` (the project field reported by `make check` when the text does not fit).

| `type` | Draws | Main keys (defaults) |
|---|---|---|
| `text` | one line | `text`, `align` (`left`, `center`, `right`), `x=2`, `shift=0`, `typed: {phase, cps, finish_at_end}`, `active`, `active_color=bright`, `inactive_text`, `tick_switch`, `fit=true`, `on_border` |
| `lines` | lines typed one after another during a phase | `items`, `phase`, `step=0.2`, `cps=110`, `prefix`, `dim_color`, `dim_negative`, `flash=0.15`, `row_step=1` |
| `bars` | label, gradient bar, percent per row | `items` (`[[label, value], …]`), `phase`, `mode` (`keep` or `rank`), `label_w`, `threshold` (required in `keep` mode), `mark` (`left` or `right`), `stagger=0.5`, `grow=0.4`, `lit_at=0.6`, `lit_color=gold`, `seeds`, `summary: {prefix, text, row, cps}` |
| `race` | candidates racing to their scores with rolling digits | `names`, `scores`, `base`, `fail`, `win`, `phase`, `winners=2`, `layout` (`inline` or `two_line`), `label_w=3`, `gap=3` |
| `stages` | status text that changes with the phase, then a progress bar | `stages: [{from, until, text, done, cps}]`, `x=3`, `label_w=26` |
| `verdict` | each candidate against the baseline, then a typed conclusion and a flash; a round whose lines do not fit with percent signs shows its scores without them | `phase`, `scores`, `base`, `version`, `line="{lab} {val} {rel} {cur}"`, `win_text`, `keep_text`, `verdict_row=4`, `cps=28.8` |
| `chips` | `[tag]` chips lit for every lesson so far, plus a counter | `labels`, `phase`, `key=learned`, `per_row=2`, `counter`, `next` |
| `sequence` | outcome symbols revealed across a phase, optional typed legend | `items`, `phase`, `max`, `spacing=2`, `cross=✗`, `legend`, `ok_color=go`, `alt_color=fb` |
| `store` | version badge, `vA → vB` while a win lands, growing entry list | `entries`, `phase`, `jump_text`, `count_key=n_ent`, `initial` (required), `layout=badge`, `show=4` |
| `kv` | pieces of text on one row | `parts: [{text, color, bold, x, show}]`; a part whose `show` binding is false is left out |
| `meter` | a bar bound to a live value with a threshold tick and readout | `value`, `threshold` (required), `label`, `width`, `ok_color`, `low_color`, `check` |
| `ports` | ripple tagline, a rule, `◆ name value` items lit during their phase | `items`, `tagline`, `item_w=16` |
| `slots` | `[name vN]` chips that flash when a round wins | `names` |
| `buttons` | `[ label ]` buttons, the current ticker step highlighted | `labels`, `bar`, `accent` |
| `viewfinder` | corner marks around a photo, a strip with a red dot, REC and the photo's quality label | `strip_row=13`, `good`, `poor` |

Overlay components (in `overlay:`):

| `type` | Draws | Main keys |
|---|---|---|
| `status` | centred status line | `row`, `items: [{key, value, after, accent}]`, `style` (`brackets` or `plain`), `gap=3` |
| `divider` | section divider: a dotted rule with a pulsing label, or a plain rule | `row`, `text`, `labels`, `style=rule`, `color=gold`, `margin=2` |
| `label` | free text at a cell | `x`, `y`, `text`, `max`, `color` |

The ticker, race, verdict, store and slots components were written for the reference animations. They are part of their templates, not a general API, and may change with them.

### wires

| Key | Meaning |
|---|---|
| `id`, `color` | identity and color |
| `path` | corner points `[[x, y], …]`; the line is drawn orthogonally between them with `┄ ┆ ╭ ╮ ╰ ╯` and junctions |
| `arrow` | `[x, y, glyph]` |
| `to` | box id that flashes when a packet arrives |
| `decay` | seconds the lit wire takes to fade after a packet (default 4) |
| `label` | `{text, x, y, anchor, blocks_packets}` text drawn on the wire |
| `pulses` | when packets run (below) |

A pulse is one of:

- `{phase, from, to, repeat, step, from_step, to_step, plus_from, plus_to, if}`: during a phase of every round; `from` and `to` are shares of the phase; `repeat` sends several, shifted by `step`; `if` is a binding that must be true for that round.
- `{at, dur}`: once, at an absolute time.
- `{every, dur, start, until}`: periodically between two named moments (`intro`, `hot` and others).

### Bindings

Strings in a scene may contain `{expression}`. The expression is evaluated per frame with these names: `round` (this round's values plus `n`), `rounds` (count), `ri` (round index from 0), `all_rounds`, `data`, `t`, `speed`, `tick` (ticker step: `k`, `u`, `conf`, `gate`, `act`, `go`), `counter`, `version`, `photo` (`ready`, `name`, `bbox`, `confident`). The builtins are limited to `tw max min len round int float str abs sum sorted enumerate range any all zip format list set dict`. A whole-string binding keeps its type (a list stays a list).

`{{field.path}}` is different: it is replaced once, when the template is loaded, by the project's value. A whole-string reference keeps the value's type. Project text is literal, so a user's `{` is never evaluated.

### ticker

| Key | Meaning |
|---|---|
| `period` | seconds per step, per round |
| `confidences` | per round: the confidence of every step, in order, from the project; step `k` shows number `k` and the list repeats |
| `threshold` | confidence at which a step goes ahead (from the project) |
| `actions` | step action names, in turn |
| `wrap_end` | replay round 1 during the outro so the last frame flows into the first |
| `pulses` | `[{wire, from, to, when}]` per step; `when` is `always`, `go` or `fallback` |

The ticker makes up no number: every confidence, and the threshold, comes from the project.

### photo layer

| Key | Meaning |
|---|---|
| `box`, `at`, `size` | the box that holds the photo, the cell offset inside it, the size in cells |
| `rounds` | per round `[photo id, quality]`; photos are listed in the project's `photos:` |
| `fx_period` | seconds per box-effect cycle, per round |
| `compare` | play a before and after split screen during the freeze |

`make play` prepares photos first (`python -m cinetty.photos project.yaml`): it crops, blurs the listed regions, detects objects with RT-DETR, outlines the main target with SAM 2 and renders the box effects as transparent PNG frames into `build/`. During playback each image is uploaded once through the Kitty graphics protocol and afterwards only placed and removed.


## scene.yaml: event driver

`driver: events` plays a board from timed events. `board:` picks the board: `circuit` (default), `workflow` or `phone`. The layout of `workflow` and `phone` lives in their Python module (`cinetty/workflow.py`, `cinetty/phone.py`); their scene file holds the palette, the timing and a `texts:` map that passes the project's fields in.

Events share one format: a mapping with `t` (seconds from the start, never decreasing) and `type`, plus the keys of that type. Events at the same time play in list order. Unknown types, unknown keys, missing keys and references to unknown boxes, wires or devices are errors.

### circuit board

| Key | Meaning |
|---|---|
| `canvas`, `duration`, `palette` | as above |
| `event_colors` | palette names allowed as event colors |
| `title` | `{text, row, field}` |
| `boxes` | `{id, rect, color, field, name, role, details}` lettered modules |
| `wires` | `{id, pts, color, arrows, labels, trim_start}`; `arrows` is a list of `[x, y, glyph]`; a label is `{at, text, field}` or right-aligned `{right_at, text, tag, field}` |
| `legend` | `{at, items: [{color, text}]}` |
| `log` | `{rect, title, lines, cps, clock_start}`; the clock is `clock_start` plus the event time, never the system clock |
| `prompt` | `{at, prefix, command, delay, cps, field}`: the command typed at the start |
| `status` | `{at, keys, live_color}`: keys with initial values; a value that differs from its initial one is drawn in `live_color` |

Event types: `pulse {wire, dur, dir, label}`, `light {box, until}`, `log {text, tag, color}`, `status {key, value}`, `highlight {box, text, color}`.

### workflow board

Keys: `canvas` (90 x 46), `duration`, `cycle` (the animation loops every `cycle` seconds), `seed` (seeds the counter ticks so playback is deterministic), `palette` (`main workers router advisor highlight`), `texts`.

Event types: `advise {until, moment, lines, who, log, log_end, hold_card}`, `log {who, text, route, card, result}`, `decision {who, text, row, p, route, card}`, `review {until}`. Routes are `plan`, `escalate`, `dispatch` and `handback`.

The board has three worker card slots, centred on columns 36, 57 and 78. The number of cards follows `texts.workers` (one to three): one card uses the middle slot, two use the outer slots, three use all of them. Unused slots, their arrows and the lines to them are not drawn, and `card` and `hold_card` in events range over the cards that exist.

### phone board

Keys: `canvas` (94 x 37), `duration`, `retention`, `ocr_seconds`, `palette` (`main ocr decision action running vision confirm empty empty_text`), `texts`.

Event types: `dispatch {to, text}`, `done {text, final}`, `ocr {boxes, ms}`, `decision {question, answer, confidence, outcome, candidates}`. An event starts at its time or when the packet before it has arrived, whichever is later.

Legacy `record` mappings in scene files are unused by terminal playback. The `record` field type in `template.yaml` is a structured data mapping, unrelated to playback.
