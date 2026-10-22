# Third-party material

cinetty's own code and templates are under the MIT license (see `LICENSE`). This file lists everything else the repository ships, downloads or uses at run time.

## Shipped in this repository

| File | What it is | Source | Author | License |
|---|---|---|---|---|
| `assets/photos/taxi-mexico.jpg` | Street photo used by `photo-loop` | [Wikimedia Commons: Taxi à Mexico](https://commons.wikimedia.org/wiki/File:Taxi_%C3%A0_Mexico.jpg), taken 2015-07-15 | Benoît Prieur | CC0 1.0 |
| `assets/photos/soho-crossing.jpg` | Street photo used by `photo-loop` | [Wikimedia Commons: People crossing street (Unsplash)](https://commons.wikimedia.org/wiki/File:People_crossing_street_(Unsplash).jpg), taken 2015-07-27 | Mike Petrucci (published on Unsplash, moved to Commons) | CC0 1.0 |
| `templates/*/preview/*`, `docs/hero.png`, `docs/hero.mp4`, `docs/hero.gif` | Example animation previews and stills | Produced from the example projects by the cinetty authors | cinetty contributors | MIT, like the code; frames that show the photos also fall under the photos' CC0 |

Both photos are full-resolution copies (3264 × 2448) with their metadata (EXIF) removed losslessly. Number plates are blurred at render time, not in the files: the blur regions are part of each example's `project.yaml`.

## Downloaded by `make setup-photo`

`make setup-photo` downloads both models into `models/` (never into the shared Hugging Face cache). They are not part of the repository.

| Model | Used for | Source | License |
|---|---|---|---|
| RT-DETR (`PekingU/rtdetr_r50vd`) | Object detection in photo templates | [Hugging Face](https://huggingface.co/PekingU/rtdetr_r50vd) | Apache-2.0 |
| SAM 2.1 tiny (`facebook/sam2.1-hiera-tiny`) | Outlines of the detected objects | [Hugging Face](https://huggingface.co/facebook/sam2.1-hiera-tiny) | Apache-2.0 |

## Python packages (installed by `make setup` and `make setup-photo`)

| Package | Used in | License |
|---|---|---|
| numpy | `cinetty/photos.py` | BSD-3-Clause; bundled notices also apply |
| pillow | `cinetty/photos.py` | MIT-CMU (HPND); bundled notices also apply |
| opencv-python-headless | `cv2` in `cinetty/photos.py` | OpenCV: Apache-2.0; Python packaging: MIT; bundled libraries include GPL and LGPL components (below) |
| torch, torchvision | model inference in `cinetty/photos.py` and their Transformers image processors | BSD-3-Clause; bundled third-party notices also apply |
| transformers, huggingface-hub | model loading in `cinetty/photos.py`; `scripts/download_models.py` | Apache-2.0 |
| pyyaml | `cinetty/template.py` | MIT |

## OpenCV wheel and bundled media libraries

The table above gives the projects' main licenses, not a single license for the whole installed environment. OpenCV's Python packaging has an [MIT license](https://github.com/opencv/opencv-python/blob/master/LICENSE.txt); its [third-party notices](https://github.com/opencv/opencv-python/blob/master/LICENSE-3RD-PARTY.txt) cover additional libraries.

On macOS Apple silicon, the installed `opencv-python-headless==5.0.0.93` wheel was checked on 2026-10-21. Its FFmpeg libraries `libavcodec`, `libavformat` and `libavutil` report `GPL version 3 or later` through their runtime license functions. The wheel also contains libx264 and libx265, identified as GPL-3.0-or-later in the dependency audit. Other bundled components include LGPL-2.1 libraries and macOS libraries libgmp, libidn2 and libunistring listed under LGPL-3.0. This describes the inspected wheel; other platform builds may differ. Keep its `cv2/LICENSE.txt`, `cv2/LICENSE-3RD-PARTY.txt` and distribution notices when distributing that wheel.

There is no call to an external `ffmpeg` or `ffprobe` executable in the remaining scripts or Python code. These executables are not installation requirements. FFmpeg libraries inside the OpenCV wheel remain covered by the notices above.

Redistributing an environment or binary bundle requires checking the exact included libraries and satisfying their licenses, including notices, license copies, applicable corresponding-source requirements, and LGPL replacement or relinking requirements. See the [FFmpeg legal guidance](https://ffmpeg.org/legal.html) and the applicable [GPL](https://www.gnu.org/licenses/gpl-3.0.html) and [LGPL](https://www.gnu.org/licenses/lgpl-3.0.html) texts. The repository's own code and templates remain MIT; that does not describe every bundled dependency.

## Fonts (used, not shipped)

| Font | Where it comes from | License |
|---|---|---|
| Sarasa Term SC (optional) | Installed by the user, for example `brew install --cask font-sarasa-gothic`. Used for Chinese text when present; otherwise the terminal uses its configured CJK fallback | SIL Open Font License 1.1 |
| Menlo | Ships with macOS; used by `cinetty/photos.py` to draw photo labels | Apple system font, used locally and not redistributed |
| DejaVu Sans Mono | User-installed Linux font checked by `cinetty/photos.py`; Pillow’s fallback is used if absent | DejaVu / Bitstream Vera font licenses; used locally, not shipped |
