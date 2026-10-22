# cinetty design

Status: revision 3 (2026-10-21), written after the templates were built. When code and this note disagree, fix the note in the same commit.

## What the repository is

cinetty is a template library for architecture and flow animations that play in a user’s terminal. It works like a pack of After Effects templates: each template is a finished animation with a fixed layout, palette and rhythm, and a set of named fields. You fill the fields with your own system; the layout does not change.

The templates come from six pieces we made in October 2026 for our own projects: a self-improving agent harness in landscape, in portrait and with real photos, an agent workflow board, a screen-flow board, and a keyboard circuit board. Each was a one-off script. cinetty turns them into one engine and six templates, so another team can describe their own system and get the same kind of video.

The intended user is a coding agent working for a person. The agent reads the person's repository, picks a template, writes one `project.yaml`, runs the check until it passes, and plays it. `AGENTS.md` is that agent's manual; `README.md` is the person's.

## The flow

```
make templates ──▶ read template.yaml ──▶ write project.yaml ──▶ make check ──▶ make play
 (purpose, preview)  (fields, limits)        (repository facts)     (field paths)   (current terminal)
```

`make check` exits non-zero and lists every problem with a code, the field path in `project.yaml`, the measured width, the limit and a hint. It never shortens, shrinks or rewraps text: a template that silently cut a label would produce a wrong video that looks right. The agent shortens the text and runs the check again.

## Layers

```
┌────────────────────────┐  {{field.path}}  ┌────────────────────────────┐
│ project.yaml (user)    │ ───────────────▶ │ template                   │
│ template, version,     │  values by type  │ template.yaml: fields,     │
│ name, fields, events   │                  │   limits, example, preview │
└────────────────────────┘                  │ scene.yaml: fixed layout   │
                                            └─────────────┬──────────────┘
                                                          │ resolved scene (plain data)
                                            ┌─────────────▼──────────────┐
                                            │ engine: render_frame(t)    │
                                            │ round driver  (scene.py)   │
                                            │ event boards  (board.py,   │
                                            │   workflow.py, phone.py)   │
                                            └─────────────┬──────────────┘
                                                          │ cells and Kitty images
                                            ┌─────────────▼──────────────┐
                                            │ player in your terminal    │
                                            └────────────────────────────┘
```

`render_frame(t)` depends only on the project and the time. Boards whose state builds up over time (the workflow and phone boards) replay their events frame by frame from the start, with seeded randomness, so the same `t` always gives the same frame. That makes four things possible: `make once` prints any frame, `make check` plays the whole timeline, a development script (not shipped) compares the engine with the original scripts cell by cell, and the live player can drop frames without drifting.

## Why values are passed by type

The template's scene file says `title: "{{title}}"` or `rounds: "{{rounds}}"`. When a reference is the whole string, the project's value goes in with its type: a list stays a list, a number stays a number. When a reference is part of a longer string, the value is inserted as escaped text. Project text is wrapped as literal, so braces a user types are never evaluated as bindings. Substituting YAML text instead would let a user's colon or quote change the structure of the scene, and a user's brace run code.

Scene strings may contain bindings such as `{round.task}` or `{max(round.part_scores):.2f}`, evaluated per frame with a fixed set of names and builtins. They belong to the template author; users never write them.

## Three engines under one interface

The round driver (`cinetty/scene.py`) plays the three harness templates: an intro, N rounds of the same phases, an all-lit hold, a freeze on a chosen frame and an outro that fades back to the first frame, so the video loops. Boxes, wires, packets and components are data in `scene.yaml`. This is the free layout: a template author can build a new round-based template without writing Python.

The event boards play timed events. The circuit board (`cinetty/board.py`) is also data-driven: modules, wires and labels are in `scene.yaml`, and its events are low-level verbs (`pulse`, `light`, `log`, `status`, `highlight`), so it fits any system with eight blocks and the same wiring. The workflow board (`cinetty/workflow.py`) and the phone board (`cinetty/phone.py`) are fixed layouts written in Python. Their originals were state machines with queues and gated packets; describing that as YAML would have produced a second programming language. Their scene files hold the palette, timing and the texts.

All event boards read one event format: `{t, type, …}` with `t` in seconds from the start. Times never go back, same-time events play in list order, and unknown types, keys and references are errors. Log clocks show a `clock_start` from the project plus the event time, never the system clock, so repeated playback is deterministic.

All templates share one visual language, so they read as a family: the rainbow spaced title with a white sweep, `■ name` legends, single-line boxes with a light running around the border (faster on the active box) and a flash when a packet arrives, dashed orthogonal wires, packets with an eight-step trail, thin and gradient bars, typed text, and a `key [value]` status line.

## Fields and checks

Every field in `template.yaml` has a type and limits: `max_cells` for text, exact or minimum and maximum item counts for lists, ranges with units for numbers, enums, references to other fields, and files. Fields are named by purpose (`decision.handoff`, `devices[1].name`), not by position. Our own content lives only in the example projects; templates have no defaults, so an agent that forgets a field gets an error instead of our text in its user's video.

Static limits do not catch everything: a candidate row's room depends on the widest outcome word, a log line's on the widest tag, and some text appears only at one moment. So the check also plays the timeline. The round driver collects every text that did not fit its slot, with the time and round, and maps it back to a field. The event boards compute their columns the same way the drawing code does and report the event path (`events[9].candidates[0].text`). Boards with fixed or limited counts (one to three workers, two devices, eight modules) report a count outside that range as an error.

## Terminal playback

`make play INPUT=project.yaml` checks the project, prepares any photos, and plays in the current terminal. `make preview` is an alias. The player waits until the terminal has enough cells, then centres the picture; Ctrl-C stops it. `LOOP=1` repeats an animation. `make once INPUT=project.yaml AT=12` prints a text frame.

`photo-loop` needs a terminal that supports the Kitty graphics protocol. The five text-only templates do not. Photo frames are uploaded once and then placed as needed; the terminal needs enough image storage for them. The phone template displays the board alone.

To keep a video, record the terminal with your own screen recorder.

Terminal fonts come from the user's terminal settings. Chinese text needs a CJK font; Sarasa Term SC is an optional choice. Photo labels use Menlo on macOS, DejaVu Sans Mono on Linux, or Pillow's fallback. No font is shipped.

## Photos and models

The photo template uses two CC0 street photos. `make setup` downloads RT-DETR (object detection) and SAM 2.1 tiny (outlines), both Apache-2.0, into `models/` inside the repository, so nothing lands in a shared cache and removing the folder removes them. Regions such as number plates are blurred at render time, from rectangles listed in the project file; the photo files themselves are unchanged apart from removed metadata.

## Parity with the originals

A development script, kept outside this repository, loads an original script read-only (it never writes a cache next to it) and compares its cells with the engine's at every step. The harness, circuit, workflow and phone templates match their originals at 100% of cells, colors included, when fed the original texts. The portrait template was compared with an earlier revision of its original, the one whose texts were kept. Pixel appearance also depends on the terminal font, the SAM 2 implementation and the example content. Parity is a development tool, not a release gate: a template may later change its look on purpose.

## What is not included

- The document renderer, the HTML slides and the phone app screens from the same month are not terminal architecture diagrams.
- A role configuration screen from the dispatch board has the same look but shows a setup form, not a flow. It could become a still template later.
- Field-level `{zh, en}` maps: one project file per language is simpler to check and to translate.

## Commands

| Command | Does |
|---|---|
| `make setup` | creates `.venv` with the declared minimum Python; installs pinned packages; downloads both models into `models/`; keeps installation caches in `.setup-cache/` |
| `make templates [FORMAT=json]` | lists templates: id, kind, output, purpose, preview |
| `make check INPUT=… [FORMAT=json]` | checks fields and events and plays the timeline |
| `make play INPUT=… [LOOP=1]` | checks, prepares photos and plays in the current terminal; `make preview` is an alias |
| `make once INPUT=… AT=12` | prints one frame |
