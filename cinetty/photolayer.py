"""The photo layer: which photo and which box-effect frame show at time ``t``, and the
Kitty graphics escapes that put them on screen.

Images are uploaded once when playback starts and afterwards only placed and
removed, so a frame costs a few bytes. The box effects are kept at 30 frames per
second (every second frame of a 60 fps render) because each terminal screen has
an image memory limit; the recorder raises Ghostty's ``image-storage-limit``.

Scene section::

  photo_layer:
    box: phone                   # the box the photo sits in
    at: [1, 1]                   # offset of the photo's top-left cell inside the box border
    size: [57, 13]               # cells
    rounds: "{[[r.photo, r.quality] for r in all_rounds]}"   # photo id and "low" or "high" per round
    fx_period: [3.6, 3.0, 2.6]   # seconds between two detection runs, per round
    compare: true                # show the closing split screen between hold and fade
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PhotoLayer:
    def __init__(self, spec, scene):
        self.S = scene
        self.spec = spec
        self.box = scene.B[spec.get("box", "phone")]
        self.at = spec.get("at", [1, 1])
        self.offset = (0, 0)             # (left, top) of the picture in the terminal, set by the player
        self.size = spec.get("size", [57, 13])
        self.rounds = [tuple(x) for x in scene.static(spec["rounds"])]
        self.period = [float(x) for x in spec.get("fx_period", [3.6, 3.0, 2.6])]
        self.compare = bool(spec.get("compare", True))
        # ``python -m cinetty.photos`` writes build/photos/<project name>.json pointing at the assets.
        pointer = ROOT / "build" / "photos" / (scene.spec.get("_meta", {}).get("name", "scene") + ".json")
        self.dir, self.meta = None, None
        if pointer.exists():
            self.dir = ROOT / "build" / "photos" / json.loads(pointer.read_text())["dir"]
            meta_path = self.dir / "photos.json"
            self.meta = json.loads(meta_path.read_text()) if meta_path.exists() else None

    # ---------------------------------------------------------- state
    def comparing(self, t):
        tl = self.S.tl
        return self.compare and tl.HOLD_S <= t < tl.FADE_S

    def current(self, t):
        """(photo id, variant) shown at ``t``; variant is "" or "-degraded"."""
        if self.comparing(t):
            return "compare", ""
        ri, _ = self.S.ticker.time(t) if self.S.ticker else (self.S.tl.round_at(t), t)
        pid, quality = self.rounds[ri]
        return pid, "-degraded" if quality == "low" else ""

    def confident(self, t):
        return self.current(t)[1] == ""

    def target(self, t):
        """Name and box (in on-screen photo pixels) of the main object of the photo shown, or None before the photos are prepared."""
        pid, _ = self.current(t)
        if not self.meta or pid not in self.meta["photos"]:
            return None
        return self.meta["photos"][pid]

    def fx_frame(self, t):
        """(set, kind, frame number) of the box-effect overlay at ``t``."""
        if not self.meta:
            return None
        tl = self.S.tl
        if self.comparing(t):
            n = self.meta["fx"]["compare"]["reveal"]
            return ("compare", "reveal", min((n - 1) // 2, int((t - tl.HOLD_S) * 30)) * 2)
        ri, tt = self.S.ticker.time(t)
        pid, quality = self.rounds[ri]
        kind = "low" if quality == "low" else "high"
        start = tl.intro if ri == 0 else min(v[0] for v in tl.PH[ri].values())
        if ri == 0 and t < tl.FADE_S:
            start = 0.0
        bt = (tt - start) % self.period[ri]
        n = self.meta["fx"][pid][kind]
        return (pid, kind, min((n - 1) // 2, int(bt * 30)) * 2)

    # ---------------------------------------------------------- terminal
    def images(self):
        """{image id: file} for every picture the layer can show."""
        out = {}
        photos = list(self.meta["photos"])
        for i, pid in enumerate(photos):
            for j, v in enumerate(("", "-degraded")):
                out[("photo", pid, v)] = (11 + i * 2 + j, self.dir / f"{pid}{v}.png")
        si = 0
        for pid, kinds in self.meta["fx"].items():
            for kind, n in kinds.items():
                for k in range(0, n, 2):
                    out[("fx", pid, kind, k)] = (1000 + si * 200 + k, self.dir / "fx" / pid / kind / f"{k:03d}.png")
                si += 1
        return out

    def upload(self):
        if not self.meta:
            return ""
        out = []
        self.ids = {}
        for key, (iid, path) in self.images().items():
            self.ids[key] = iid
            data = base64.standard_b64encode(path.read_bytes()).decode()
            for i in range(0, len(data), 4000):
                ctl = f"a=t,f=100,t=d,i={iid},q=2," if i == 0 else ""
                out.append(f"\x1b_G{ctl}m={1 if i + 4000 < len(data) else 0};{data[i:i + 4000]}\x1b\\")
        return "".join(out)

    def _place(self, iid, placement, z):
        b = self.box
        left, top = self.offset
        row, col = b.y0 + int(self.at[1]) + 1 + top, b.x0 + int(self.at[0]) + 1 + left
        return (f"\x1b[{row};{col}H\x1b_Ga=p,i={iid},p={placement},c={self.size[0]},r={self.size[1]},"
                f"z={z},C=1,q=2\x1b\\")

    def update(self, t, shown):
        """Escapes that move the screen from ``shown`` (photo, fx) to what ``t`` needs. -> (escapes, new shown)."""
        if not self.meta:
            return "", shown
        photo = ("photo",) + self.current(t)
        f = self.fx_frame(t)
        fx = ("fx",) + f if f else None
        out = []
        old_p, old_f = shown or (None, None)
        if photo != old_p:
            if old_p is not None:
                out.append(f"\x1b_Ga=d,d=i,i={self.ids[old_p]},p=1,q=2\x1b\\")
            out.append(self._place(self.ids[photo], 1, -1073741900))
        if fx != old_f:
            if old_f is not None:
                out.append(f"\x1b_Ga=d,d=i,i={self.ids[old_f]},p=2,q=2\x1b\\")
            if fx is not None:
                out.append(self._place(self.ids[fx], 2, -1073741850))
        return "".join(out), (photo, fx)
