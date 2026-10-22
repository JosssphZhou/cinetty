"""Prepare the photo layer: crop and obscure photos, detect objects, outline them, render box effects.

  python -m cinetty.photos PROJECT.yaml [--force]

For each entry in ``fields.photos`` of the project this writes, under
``build/photos/<project name>/``:

  <id>.png, <id>-degraded.png     the photo in gray (1824x780) and a darker, flatter copy
  fx/<id>/high/NNN.png            transparent box-effect frames (all objects, confident)
  fx/<id>/low/NNN.png             the same, unsure: three objects, orange, shaking
  compare.png, fx/compare/reveal  the closing split screen (unsure left, confident right)
  photos.json                     the main object per photo and the frame counts

Detection uses RT-DETR and outlines use SAM 2.1, both Apache-2.0, loaded from
``models/`` (``make setup-photo`` downloads them). Labels in the frames use a system monospace
font (Menlo on macOS, DejaVu Sans Mono on Linux); no font ships with this repository.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import template as T

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def require_photo_setup():
    """Check optional packages and weights before preparing uncached photo assets."""
    packages = ("torch", "torchvision", "transformers", "huggingface_hub", "cv2")
    models = (MODELS / "rtdetr_r50vd", MODELS / "sam2.1-hiera-tiny")
    if (any(importlib.util.find_spec(p) is None for p in packages)
            or any(not (m / "config.json").is_file() or not any(m.glob("*.safetensors")) for m in models)):
        raise SystemExit("cinetty: photo preparation needs optional dependencies and local models. Run: make setup-photo")


W, H = 1824, 780                       # twice the on-screen size (57 x 13 cells of 16 x 30 px)
LOW_BOXES = 3                          # boxes drawn on an unsure photo
CYAN, ORANGE, WHITE = (40, 240, 255), (255, 145, 40), (255, 255, 255)
PALETTE = [(255, 60, 210), (255, 225, 40), (90, 255, 120), (120, 150, 255), (255, 100, 90), (190, 120, 255),
           (60, 220, 160), (255, 170, 60)]
# Bold monospace fonts for the labels drawn on the photos, first one found wins: Menlo on
# macOS, DejaVu Sans Mono on most Linux systems; Pillow's own font otherwise.
BOLD_FONTS = [("/System/Library/Fonts/Menlo.ttc", 1),
              ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 0),
              ("/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf", 0),
              ("/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf", 0)]
# For text the monospace fonts have no glyphs for (Chinese, Japanese, Korean captions): Hiragino
# Sans GB W6 or STHeiti on macOS, Noto Sans CJK on Linux.
WIDE_FONTS = [("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
              ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
              ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
              ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", 0),
              ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc", 0)]


def quiet_models():
    """Keep model loading quiet: no progress bars, no notices about checkpoint variants."""
    import logging
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)
    import transformers
    transformers.utils.logging.disable_progress_bar()


def has_glyphs(font, text):
    """True when the font draws every character of text, instead of its empty-box glyph."""
    def drawn(ch):
        im = Image.new("L", (2 * font.size, 2 * font.size))
        ImageDraw.Draw(im).text((0, 0), ch, font=font, fill=255)
        return im.tobytes()

    box = drawn("\U0010fffd")
    return all(ch.isspace() or drawn(ch) != box for ch in text)


def headline_x(font, txt, W):
    """Left edge of the comparison headline: the arrow of "before → after" sits on the divider in
    the middle, so a longer side never runs under it."""
    before, sep, after = txt.partition(" → ")
    if not sep or font.getlength(before) == font.getlength(after):
        return (W - int(font.getlength(txt))) // 2
    return int(round(W / 2 - font.getlength(before + " ") - font.getlength("→") / 2))


def bold(n, text=""):
    """A bold font of size n that has glyphs for text: a monospace one when it can draw the text."""
    fonts = [ImageFont.truetype(path, n, index=index) for path, index in BOLD_FONTS + WIDE_FONTS if os.path.exists(path)]
    for font in fonts:
        if has_glyphs(font, text):
            return font
    return fonts[0] if fonts else ImageFont.load_default(n)


def c01(x):
    return max(0.0, min(1.0, x))


def ease_out_back(u, s=2.0):
    u = max(0.0, min(1.0, u)) - 1
    return 1 + (s + 1) * u ** 3 + s * u ** 2


# ------------------------------------------------------------------ photos
def prepare_image(src, crop, blur):
    """Obscure ``blur`` rectangles (source pixels), crop, scale to W x H. -> (color, gray, degraded)."""
    full = Image.open(src).convert("RGB")
    f = full.width / 1920
    for bb in blur:
        bb = tuple(int(v) for v in bb)
        r = full.crop(bb).filter(ImageFilter.GaussianBlur(14 * f))
        full.paste(Image.eval(r, lambda v: int(v * 0.6)), bb[:2])
    img = full.crop(tuple(int(v) for v in crop)).resize((W, H), Image.LANCZOS)
    gray = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=2))
    g = np.array(gray).astype(float)
    g = 255 * (g / 255) ** 1.08
    ok = Image.fromarray(g.clip(0, 255).astype(np.uint8)).convert("RGB")
    dark = Image.fromarray((12 + g * 0.30).clip(0, 255).astype(np.uint8)).convert("RGB")
    return img, ok, dark


def detect(img, threshold=0.5):
    quiet_models()
    import torch
    from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
    d = MODELS / "rtdetr_r50vd"
    proc = RTDetrImageProcessor.from_pretrained(d)
    model = RTDetrForObjectDetection.from_pretrained(d).eval()
    with torch.no_grad():
        out = model(**proc(images=img, return_tensors="pt"))
    res = proc.post_process_object_detection(out, target_sizes=torch.tensor([img.size[::-1]]), threshold=threshold)[0]
    dets = [dict(name=model.config.id2label[int(lb)], conf=round(float(s), 2), box=[round(float(v)) for v in b])
            for s, lb, b in zip(res["scores"], res["labels"], res["boxes"])]
    dets.sort(key=lambda d: -d["conf"])
    return dets


def outline(img, dets, hints):
    """Add ``poly`` (outer contour, about 220 points) to each detection with SAM 2.1."""
    import cv2
    quiet_models()
    import torch
    from transformers import Sam2Model, Sam2Processor
    d = MODELS / "sam2.1-hiera-tiny"
    proc = Sam2Processor.from_pretrained(d)
    model = Sam2Model.from_pretrained(d).eval()
    arr = img
    for det in dets:
        x1, y1, x2, y2 = det["box"]
        kw = {}
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        for h in hints:
            bx1, by1, bx2, by2 = h["region"]
            if bx1 <= cx <= bx2 and by1 <= cy <= by2 and det["name"] == h.get("class", "person"):
                pts = [[float(x), float(y)] for x, y in h["points"]]
                kw = dict(input_points=[[pts]], input_labels=[[[1] * len(pts)]])
        inputs = proc(images=arr, input_boxes=[[[float(v) for v in det["box"]]]], return_tensors="pt", **kw)
        with torch.no_grad():
            out = model(**inputs, multimask_output=False)
        masks = proc.post_process_masks(out.pred_masks, inputs["original_sizes"])[0]
        m = masks[0, 0].numpy().astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cs:
            det["poly"] = []
            continue
        cc = max(cs, key=cv2.contourArea).reshape(-1, 2)
        det["poly"] = cc[:: max(1, len(cc) // 220)].tolist()
    return dets


def order(dets, focus=None):
    """Main object first (the first of class ``focus``, else the most confident), then the rest by size."""
    dets = [d for d in dets if d["poly"] and (d["box"][2] - d["box"][0]) >= 14]
    main = next((i for i, d in enumerate(dets) if d["name"] == focus), 0) if focus else 0
    dets.insert(0, dets.pop(main))
    others = sorted(dets[1:], key=lambda d: -(d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]))
    dets = [dets[0]] + others
    for i, d in enumerate(dets):
        d["idx"] = i + 1
        d["col"] = CYAN if i == 0 else PALETTE[(i - 1) % len(PALETTE)]
    return dets


# ------------------------------------------------------------------ box effects
def glow(mask, col, radius, gain):
    g = np.array(mask.filter(ImageFilter.GaussianBlur(radius)), float) * gain
    a = np.zeros((H, W, 4), np.uint8)
    a[..., :3] = col
    a[..., 3] = np.clip(g, 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def poly_partial(poly, p):
    pts = poly + [poly[0]]
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    lim = sum(seg) * p
    out, acc = [pts[0]], 0.0
    for (a, b), sl in zip(zip(pts, pts[1:]), seg):
        if acc + sl <= lim:
            out.append(b)
            acc += sl
        else:
            f = (lim - acc) / max(sl, 1e-6)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            break
    return out


def hatch_layer(poly, col, alpha_fill, alpha_line, step=18, wdt=3):
    fm = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fm).polygon([tuple(p) for p in poly], fill=255)
    hm = Image.new("L", (W, H), 0)
    dh = ImageDraw.Draw(hm)
    for k in range(-H, W, step):
        dh.line([(k, 0), (k + H, H)], fill=255, width=wdt)
    a = np.minimum(np.array(fm), np.array(hm)).astype(float) * alpha_line + np.array(fm, float) * alpha_fill
    lay = np.zeros((H, W, 4), np.uint8)
    lay[..., :3] = col
    lay[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(lay)


def solid(mask, col):
    sol = np.zeros((H, W, 4), np.uint8)
    sol[..., :3] = col
    sol[..., 3] = np.array(mask)
    return Image.fromarray(sol)


def label_text(name, conf):
    """Class name and the confidence the project gives; the name alone when it gives none."""
    return name if conf is None else f"{name} {conf:.2f}"


def render_fx(t, dets, low, conf, shown):
    """Transparent layer at ``t`` seconds: a scan light, a locking frame and outline on the main
    object, numbered boxes popping in on the others. ``low`` is the unsure version. ``conf`` is the
    confidence of every box in order, or None to draw the boxes without numbers."""
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = ORANGE if low else None
    sc = c01(t / 0.30)
    if t < 0.36:
        x = -80 + (W + 320) * sc
        xs = np.arange(W)[None, :].repeat(H, 0).astype(float)
        d = x - xs
        a = np.where((d >= 0) & (d < 340), np.clip(1 - d / 340, 0, 1) ** 1.6 * 150, 0) + np.where((d < 0) & (d > -12), 200, 0)
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[..., :3] = base or CYAN
        rgba[..., 3] = np.clip(a * (1 - c01((t - 0.30) / 0.06)), 0, 255).astype(np.uint8)
        cv.alpha_composite(Image.fromarray(rgba))
    jit = (0.0, 0.0)
    if low and t > 0.6:
        jit = (6.4 * math.sin(2 * math.pi * 17 * t), 4.4 * math.sin(2 * math.pi * 23 * t + 1.0))
    placed = []
    FT, FS = bold(30), bold(21)
    for i, d in enumerate(dets[:shown]):
        col = base or d["col"]
        main = i == 0
        x1, y1, x2, y2 = d["box"]
        cf = None if conf is None else conf[i]
        if main:
            u = (t - 0.22) / 0.36
            if u > 0:
                e = ease_out_back(u)
                Lc = int(min(80, 0.3 * min(x2 - x1, y2 - y1)) + 20)
                ends = [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]
                starts = [(0, 0), (W, 0), (0, H), (W, H)]
                m, wm = Image.new("L", (W, H), 0), Image.new("L", (W, H), 0)
                dm, dw = ImageDraw.Draw(m), ImageDraw.Draw(wm)
                for (ex, ey, sx_, sy_), (stx, sty) in zip(ends, starts):
                    px, py = stx + (ex - stx) * e + jit[0], sty + (ey - sty) * e + jit[1]
                    for dd, w_ in ((dm, 12), (dw, 8)):
                        dd.line([(px, py), (px + sx_ * Lc, py)], fill=255, width=w_)
                        dd.line([(px, py), (px, py + sy_ * Lc)], fill=255, width=w_)
                cv.alpha_composite(glow(m, col, 12, 2.2))
                cv.alpha_composite(solid(m, col))
                if u >= 1:
                    fl = max(0.0, 1 - (u - 1) / 0.28)
                    if fl > 0:
                        wh = np.zeros((H, W, 4), np.uint8)
                        wh[..., :3] = WHITE
                        wh[..., 3] = (np.array(wm, float) * fl).astype(np.uint8)
                        cv.alpha_composite(glow(wm, WHITE, 10, 2.0 * fl))
                        cv.alpha_composite(Image.fromarray(wh))
            pu = c01((t - 0.58) / 0.38)
            if pu > 0:
                m = Image.new("L", (W, H), 0)
                ImageDraw.Draw(m).line([tuple(p) for p in poly_partial(d["poly"], pu)], fill=255, width=6, joint="curve")
                cv.alpha_composite(glow(m, col, 8, 2.0))
                cv.alpha_composite(solid(m, col))
                hu = c01((t - 0.96) / 0.2)
                if hu > 0:
                    cv.alpha_composite(hatch_layer(d["poly"], col, 0.10 * hu, 0.42 * hu))
            l0 = 0.88
        else:
            k = i - 1
            t0 = 0.45 + 0.06 * k
            u = c01((t - t0) / 0.2)
            if u <= 0:
                continue
            e = ease_out_back(u, 1.7)
            gx, gy = (x1 + x2) / 2, (y1 + y2) / 2
            f = 1 + (1 - e) * 0.14
            bx1, bx2 = gx - (gx - x1) * f, gx + (x2 - gx) * f
            by1, by2 = gy - (gy - y1) * f, gy + (y2 - gy) * f
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dl = ImageDraw.Draw(lay)
            if t > t0 + 0.1:
                cp = c01((t - t0 - 0.1) / 0.3)
                cv.alpha_composite(hatch_layer(d["poly"], col, 0.10 * cp, 0.0))
                dl.line([tuple(p) for p in poly_partial(d["poly"], cp)], fill=col + (200,), width=3, joint="curve")
            dl.rectangle([bx1 + jit[0], by1 + jit[1], bx2 + jit[0], by2 + jit[1]], outline=col + (int(255 * u),), width=3)
            cv.alpha_composite(lay)
            l0 = t0 + 0.06
        # Numbered square at the top left, class and confidence next to it.
        lu = c01((t - l0) / 0.14) if main else c01((t - l0) / 0.12)
        if lu > 0:
            sq = 56 if main else 34
            fnt = FT if main else bold(24)
            txt = label_text(d["name"], cf)
            tfont = FT if main else FS
            tw_ = int(tfont.getlength(txt))
            bar_w = 80 if main and cf is not None else 0
            lw = tw_ + 18 + (bar_w + 14 if bar_w else 0)
            tx0 = int(max(2, min(x1, W - sq - lw - 6)))
            cands = [(tx0, int(y1 - sq - 4))] + [(tx0, int(y1 + 4 + k * (sq + 4))) for k in range(4)] \
                + [(tx0, int(y1 - sq - 4 - k * (sq + 4))) for k in range(1, 4)]
            tx, ty = cands[0]
            for (cx_, cy_) in cands:
                if cy_ < 2 or cy_ + sq > H - 2:
                    continue
                if all(not (cx_ < ox1 and cx_ + sq + lw > ox0 and cy_ < oy1 and cy_ + sq > oy0) for (ox0, oy0, ox1, oy1) in placed):
                    tx, ty = cx_, cy_
                    break
            ty = max(2, ty)
            tx, ty = int(tx + jit[0] * 0.5), int(ty + (1 - ease_out_back(lu, 1.2)) * 12 + jit[1] * 0.5)
            placed.append((tx, ty, tx + sq + lw, ty + sq))
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dl = ImageDraw.Draw(lay)
            a_ = int(255 * lu)
            dl.rectangle([tx, ty, tx + sq, ty + sq], fill=col + (a_,))
            dl.text((tx + sq / 2, ty + sq / 2), str(d["idx"]), font=fnt, fill=(0, 0, 0, a_), anchor="mm")
            lx = tx + sq + 2
            if main:
                dl.rectangle([lx, ty, lx + lw, ty + sq], fill=col + (a_,))
                dl.text((lx + 10, ty + sq / 2), txt, font=tfont, fill=(0, 0, 0, a_), anchor="lm")
                if bar_w:
                    px0 = lx + 10 + tw_ + 14
                    dl.rectangle([px0 - 2, ty + 16, px0 + bar_w + 2, ty + sq - 16], fill=(0, 0, 0, int(235 * lu)))
                    pf = c01((t - (l0 + 0.06)) / 0.25) * cf
                    dl.rectangle([px0 + 2, ty + 20, px0 + 2 + int((bar_w - 4) * pf), ty + sq - 20], fill=col + (a_,))
            else:
                dl.rectangle([lx, ty, lx + lw - 14, ty + sq], fill=(0, 0, 0, int(190 * lu)), outline=col + (int(200 * lu),), width=2)
                dl.text((lx + 9, ty + sq / 2), txt, font=tfont, fill=col + (a_,), anchor="lm")
            cv.alpha_composite(lay)
    return cv


def low_boxes(photo, n_dets):
    """(confidences, boxes drawn) of the unsure version: the project's ``low_confidences``, or None
    (boxes without numbers) when it gives none."""
    lc = [float(x) for x in photo["low_confidences"]] if photo.get("low_confidences") else None
    return lc, min(len(lc) if lc else LOW_BOXES, n_dets)


def write_fx(out, dets, low, conf, shown):
    """Render a box-effect clip at 60 fps and keep every second frame (the terminal's image memory is limited)."""
    n = int((0.45 + 0.06 * (shown - 1) + 0.2 + 0.7) * 60) if shown > 1 else 84
    n = max(n, 96 if low else 90)
    n += n % 2
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    for fr in range(0, n, 2):
        render_fx(fr / 60, dets, low, conf, shown).save(out / f"{fr:03d}.png", compress_level=3)
    return n


# ------------------------------------------------------------------ closing comparison
def write_compare(out, ok, dark, dets, spec):
    """Split screen of one photo: unsure (dark, three orange boxes) left, confident right."""
    HALF = W // 2
    S, OX, OY = 0.7, int(spec.get("offset_x", 330)), 120
    base = Image.new("RGB", (W, H), (0, 0, 0))
    for k, im in enumerate((dark, ok)):
        sm = im.resize((round(W * S), round(H * S)), Image.LANCZOS).crop((OX, 0, OX + HALF, round(H * S)))
        base.paste(sm, (k * HALF, OY))
    ImageDraw.Draw(base).rectangle([HALF - 2, 0, HALF + 1, H], fill=(255, 255, 255))
    base.save(out / "compare.png")
    base.save(out / "compare-degraded.png")

    def tp(x, y, k):
        return (x * S - OX + k * HALF, y * S + OY)

    def side(k, p, shown, conf, low):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        FT, FS = bold(30), bold(18)
        for i, d in reversed(list(enumerate(dets[:shown]))):
            col = ORANGE if low else d["col"]
            main = i == 0
            pu = c01((p - (0.05 if main else 0.12 + 0.025 * i)) / 0.3)
            if pu <= 0:
                continue
            x1, y1 = tp(d["box"][0], d["box"][1], k)
            x2, y2 = tp(d["box"][2], d["box"][3], k)
            dl.rectangle([x1, y1, x2, y2], outline=col + (int(255 * pu),), width=5 if main else 3)
            pp = [tp(x, y, k) for x, y in d["poly"]]
            if main:
                dl.line(poly_partial(pp, c01((p - 0.15) / 0.5)), fill=col + (255,), width=6, joint="curve")
                hu = c01((p - 0.6) / 0.3)
                if hu > 0:
                    lay.alpha_composite(hatch_layer(pp, col, 0.10 * hu, 0.42 * hu))
            else:
                dl.line(pp + [pp[0]], fill=col + (int(160 * pu),), width=2)
            sq = 40 if main else 28
            tx, ty = int(x1) + 3, int(y1) + 3
            dl.rectangle([tx, ty, tx + sq, ty + sq], fill=col + (int(255 * pu),))
            dl.text((tx + sq / 2, ty + sq / 2), str(d["idx"]), font=FT if main else FS, fill=(0, 0, 0, int(255 * pu)), anchor="mm")
            if main:
                txt = f"{d['name']} {conf:.2f}"
                tw_ = int(FT.getlength(txt)) + 18
                dl.rectangle([tx + sq + 2, ty, tx + sq + 2 + tw_, ty + sq], fill=col + (int(255 * pu),))
                dl.text((tx + sq + 12, ty + sq / 2), txt, font=FT, fill=(0, 0, 0, int(255 * pu)), anchor="lm")
        g = lay.filter(ImageFilter.GaussianBlur(8))
        ga = np.array(g)
        ga[..., 3] = np.clip(ga[..., 3].astype(float) * 1.3, 0, 255).astype(np.uint8)
        res = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        res.alpha_composite(Image.fromarray(ga))
        res.alpha_composite(lay)
        a = np.array(res)
        a[:, : k * HALF, 3] = 0
        a[:, (k + 1) * HALF:, 3] = 0
        return Image.fromarray(a)

    F_LEFT, F_RIGHT, F_BIG = bold(46, spec["left_caption"]), bold(46, spec["right_caption"]), bold(104, spec["headline"])
    rev = out / "fx" / "compare" / "reveal"
    rev.mkdir(parents=True, exist_ok=True)
    for f in rev.glob("*.png"):
        f.unlink()
    lo, hi = float(spec["low_confidence"]), float(spec["high_confidence"])
    nf = 18
    for n in range(nf):
        p = n / (nf - 1)
        cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for k, (shown, conf, low) in enumerate(((LOW_BOXES, lo, True), (len(dets), hi, False))):
            cv.alpha_composite(side(k, p, shown, conf, low))
        dd = ImageDraw.Draw(cv)
        cu = c01((p - 0.4) / 0.4)
        for k, (txt, col, font) in enumerate(((spec["left_caption"], ORANGE, F_LEFT), (spec["right_caption"], CYAN, F_RIGHT))):
            w_ = int(font.getlength(txt))
            dd.text((k * HALF + (HALF - w_) // 2, 692), txt, font=font, fill=col + (int(255 * cu),))
        bu = c01((p - 0.5) / 0.4)
        if bu > 0:
            txt = spec["headline"]
            dd.text((headline_x(F_BIG, txt, W), 4), txt, font=F_BIG, fill=(255, 255, 255, int(255 * bu)))
        cv.save(rev / f"{2 * n:03d}.png")
    return 2 * nf


# ------------------------------------------------------------------ driver
def build_dir(name):
    return ROOT / "build" / "photos" / name


def prepare(project, force=False, log=print):
    name, data, path = T.read_project(project)
    fields = data.get("fields") or {}
    photos = fields.get("photos") or []
    if not photos:
        return None
    # Assets are stored by content, so projects with the same photos (one per language) share them.
    h = hashlib.sha256(json.dumps([photos, fields.get("compare"), [r.get("quality") for r in fields.get("rounds") or []]],
                                  sort_keys=True).encode())
    for p in photos:
        h.update(((path.parent / p["file"]).resolve()).read_bytes())
    key = h.hexdigest()[:16]
    out = ROOT / "build" / "photos" / key
    pointer = build_dir(data.get("name") or path.stem).with_suffix(".json")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    meta_path = out / "photos.json"
    if not force and meta_path.exists():
        pointer.write_text(json.dumps({"dir": key}))
        return out
    require_photo_setup()
    out.mkdir(parents=True, exist_ok=True)
    meta = {"key": key, "size": [W // 2, H // 2], "photos": {}, "fx": {}}
    lows = {r.get("photo") for r in fields.get("rounds") or [] if r.get("quality") == "low"}
    all_dets = {}
    for p in photos:
        pid = p["id"]
        src = (path.parent / p["file"]).resolve()
        color, ok, dark = prepare_image(src, p["crop"], p.get("blur") or [])
        ok.save(out / f"{pid}.png")
        dark.save(out / f"{pid}-degraded.png")
        log(f"photo {pid}: detecting objects")
        dets = detect(color, float(p.get("threshold", 0.5)))
        # Hints are given in source pixels; the models see the cropped, scaled image.
        cx0, cy0, cx1, cy1 = p["crop"]
        sx, sy = W / (cx1 - cx0), H / (cy1 - cy0)
        hints = [{"class": h.get("class", "person"),
                  "region": [(h["region"][0] - cx0) * sx, (h["region"][1] - cy0) * sy,
                             (h["region"][2] - cx0) * sx, (h["region"][3] - cy0) * sy],
                  "points": [[(x - cx0) * sx, (y - cy0) * sy] for x, y in h["points"]]} for h in p.get("hints") or []]
        log(f"photo {pid}: outlining {len(dets)} objects")
        dets = order(outline(np.array(color), dets, hints), p.get("focus"))
        all_dets[pid] = dets
        conf = [d["conf"] for d in dets]
        if p.get("main_confidence") is not None:
            conf[0] = float(p["main_confidence"])
        fx = {"high": write_fx(out / "fx" / pid / "high", dets, False, conf, len(dets))}
        if pid in lows:
            lc, shown = low_boxes(p, len(dets))
            fx["low"] = write_fx(out / "fx" / pid / "low", dets, True, lc, shown)
        meta["fx"][pid] = fx
        main = dets[0]
        meta["photos"][pid] = {"name": main["name"], "box": [round(v / 2) for v in main["box"]],
                               "objects": len(dets)}
        log(f"photo {pid}: {len(dets)} objects, main {main['name']}")
    cmp = fields.get("compare")
    if cmp:
        pid = cmp["photo"]
        ok = Image.open(out / f"{pid}.png").convert("RGB")
        dark = Image.open(out / f"{pid}-degraded.png").convert("RGB")
        meta["fx"]["compare"] = {"reveal": write_compare(out, ok, dark, all_dets[pid], cmp)}
        meta["photos"]["compare"] = dict(meta["photos"][pid])
    (out / "detections.json").write_text(json.dumps(all_dets))
    meta_path.write_text(json.dumps(meta, indent=1))
    pointer.write_text(json.dumps({"dir": key}))
    return out


def main():
    ap = argparse.ArgumentParser(prog="python -m cinetty.photos")
    ap.add_argument("project")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    out = prepare(a.project, a.force)
    print(out or "this project has no photos")


if __name__ == "__main__":
    main()
