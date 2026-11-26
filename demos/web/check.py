"""Screenshots and measurements of the web demo (css.html, phaser.html) in headless Chrome.

    python3 demos/web/check.py [--dpr 1,2,3] [--pages css,phaser] [--out DIR] [--docs]

Serves this folder on a free localhost port, opens each page at each device pixel ratio in headless Chrome (a fresh
profile each time; WebGL through SwiftShader), waits until the page sets `window.nkReady` (every sprite loaded and
drawn - a plain `--screenshot` fires before CSS images arrive), captures it over the DevTools protocol and measures
the page's probes (`#nk-probes`: each probe's logical box in CSS px):

* corners: where the texture scale equals the device pixel ratio, the sprite's top-left and bottom-right slice
  blocks on screen against the PNGs (the stacked outputs composited over the probe background), max / mean abs
  difference in 8-bit levels - 1:1 texels give ~0;
* size: each probe's drawn bounding box in CSS px (device px / ratio): the same at every ratio.

Needs Google Chrome and the `websockets` package (and network for Phaser from jsDelivr). `--docs` also writes
docs/images/web_css_demo.png and docs/images/web_phaser_demo.png (ratio 2). Run ./regenerate.sh first.
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SIZES = {"css": (880, 1360), "phaser": (880, 1360)}
PROBE_BG = (255, 255, 255)
# the ramp both pages put on the `shade` probe (css.html: SVG filter #ramp-gold; phaser-demo.js: GOLD)
PROBE_RAMPS = {"shade": [[0, "#4A2306"], [0.5, "#C8761E"], [1, "#FFF1B8"]]}


# ----------------------------------------------------------------------------------------------- serving + chrome

def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    class Server(http.server.ThreadingHTTPServer):
        # the default listen backlog (5) resets connections when Chrome / Phaser's loader fetch dozens of sprites
        # at once (net::ERR_CONNECTION_RESET, blank pieces); `python3 -m http.server` has the same limit
        request_queue_size = 256
        daemon_threads = True

    httpd = Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(HERE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


class Chrome:
    """One headless Chrome with a fresh profile, driven over the DevTools protocol."""

    def __init__(self, width: int, height: int, dpr: float):
        from websockets.sync.client import connect

        self.dir = tempfile.mkdtemp(prefix="ninekit-chrome-")
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--user-data-dir={self.dir}", "--no-first-run", "--no-default-browser-check",
             "--hide-scrollbars", "--remote-debugging-port=0", f"--window-size={width},{height}",
             f"--force-device-scale-factor={dpr}", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.dir) / "DevToolsActivePort"
        for _ in range(200):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.05)
        port = int(port_file.read_text().split()[0])
        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
        ws = next(p["webSocketDebuggerUrl"] for p in pages if p["type"] == "page")
        self.ws = connect(ws, max_size=None)
        self.n = 0

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            shutil.rmtree(self.dir, ignore_errors=True)


def capture(url: str, dpr: float, size: tuple, png: Path, timeout: float = 120.0) -> dict:
    """Opens [url], waits for window.nkReady, saves a screenshot to [png]; returns the page's #nk-probes JSON."""
    c = Chrome(size[0], size[1], dpr)
    try:
        c.call("Page.enable")
        c.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=dpr,
               mobile=False)
        c.call("Page.navigate", url=url)
        t0 = time.time()
        while not c.eval("window.nkReady === true"):
            if time.time() - t0 > timeout:
                err = c.eval("String(window.nkError || '')")
                raise RuntimeError(f"{url}: not ready after {timeout:.0f} s {err}")
            time.sleep(0.1)
        c.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        shot = c.call("Page.captureScreenshot", format="png")
        png.write_bytes(base64.b64decode(shot["data"]))
        return json.loads(c.eval("document.getElementById('nk-probes').textContent"))
    finally:
        c.close()


# ----------------------------------------------------------------------------------------------- measuring

def load_pieces() -> dict:
    """piece name -> (manifest piece, folder) from the css exports (the phaser ones carry the same files)."""
    out = {}
    for d in (HERE / "generated" / "css").iterdir():
        m = json.loads((d.parent.parent / "phaser" / d.name / "ninekit-phaser.json").read_text())
        for name, p in m["pieces"].items():
            out[name] = (p, d)
    return out


def ramp_lut(stops) -> np.ndarray:
    """256 x 3 lookup of a shade ramp (linear between stops, t = shade 0..1)."""
    ts = np.array([float(t) for t, _ in stops])
    cols = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for _, c in stops], np.float64)
    v = np.arange(256) / 255.0
    return np.stack([np.interp(v, ts, cols[:, j]) for j in range(3)], axis=1)


def composite(p: dict, folder: Path, scale: str, bg, ramp=None) -> np.ndarray:
    """The piece's stacked outputs at [scale] over [bg], float RGB; [ramp] maps a shade piece's greys first."""
    f0 = p["outputs"][p["layers"][0]][scale]
    w, h = f0["size_px"]
    rgb = np.empty((h, w, 3), np.float64)
    rgb[:] = bg
    for o in p["layers"]:
        a = np.asarray(Image.open(folder / p["outputs"][o][scale]["file"]).convert("RGBA")).astype(np.float64)
        if ramp is not None:
            a[..., :3] = ramp_lut(ramp)[a[..., 0].astype(int)]
        al = a[..., 3:4] / 255.0
        rgb = a[..., :3] * al + rgb * (1 - al)
    return rgb


def measure(png: Path, probes: dict, dpr: float, pieces: dict) -> list[dict]:
    img = np.asarray(Image.open(png).convert("RGB")).astype(np.float64)
    rows = []
    for pid, pr in probes["probes"].items():
        p, folder = pieces[pr["piece"]]
        oh = p["overhang"] or [0, 0, 0, 0]
        # the sprite rect in device px: the box plus the overhang; on a `fixed` axis the natural length, centred
        # on the box (DESIGN 7)
        rect = []
        for axis, (pos, length) in enumerate(((pr["x"], pr["w"]), (pr["y"], pr["h"]))):
            o0, o1 = oh[axis], oh[axis + 2]
            if p["slice"] is not None and p["stretch"][axis] == "fixed":
                start = pos + (length - (p["size"][axis] - o0 - o1)) / 2 - o0
                rect += [start * dpr, (start + p["size"][axis]) * dpr]
            else:
                rect += [(pos - o0) * dpr, (pos + length + o1) * dpr]
        x0, x1, y0, y1 = rect
        row = {"probe": pid, "piece": pr["piece"], "dpr": dpr}
        # drawn bounding box (pixels that differ from the probe background), CSS px
        m = int(round(2 * dpr))         # 2 CSS px around the sprite rect (captions sit 6 CSS px below)
        X0, Y0 = max(0, int(x0) - m), max(0, int(y0) - m)
        X1, Y1 = min(img.shape[1], int(np.ceil(x1)) + m), min(img.shape[0], int(np.ceil(y1)) + m)
        region = img[Y0:Y1, X0:X1]
        ys, xs = np.nonzero(np.abs(region - PROBE_BG).max(axis=2) > 8)
        if len(xs):
            row["bbox_css"] = [round(float(v), 2) for v in ((xs.min() + X0) / dpr, (ys.min() + Y0) / dpr,
                                                             (xs.max() + 1 - xs.min()) / dpr,
                                                             (ys.max() + 1 - ys.min()) / dpr)]
        else:
            row["bbox_css"] = None
        sk = str(int(dpr)) if float(dpr).is_integer() else str(dpr)
        f0 = p["outputs"][p["layers"][0]].get(sk)
        if f0 is None or pr.get("pressed"):
            rows.append(row)
            continue
        ramp = PROBE_RAMPS.get(pid) if p.get("mode") == "shade" else None
        ref = composite(p, folder, sk, PROBE_BG, ramp)
        H, W = ref.shape[:2]
        ix0, iy0, ix1, iy1 = (int(round(v)) for v in (x0, y0, x1, y1))
        row["edge_frac"] = round(max(abs(v - round(v)) for v in (x0, y0, x1, y1)), 3)
        if f0["slice_px"] is None:
            got = img[iy0:iy0 + H, ix0:ix0 + W]
            if got.shape == ref.shape:
                d = np.abs(got - ref)
                row["whole"] = [round(float(d.max()), 1), round(float(d.mean()), 2)]
        else:
            l, t, r, b = f0["slice_px"]
            tl = np.abs(img[iy0:iy0 + t, ix0:ix0 + l] - ref[:t, :l])
            br = np.abs(img[iy1 - b:iy1, ix1 - r:ix1] - ref[H - b:, W - r:])
            row["corner_tl"] = [round(float(tl.max()), 1), round(float(tl.mean()), 2)]
            row["corner_br"] = [round(float(br.max()), 1), round(float(br.mean()), 2)]
        rows.append(row)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dpr", default="1,2,3")
    ap.add_argument("--pages", default="css,phaser")
    ap.add_argument("--out", default=None, help="folder for screenshots and measurements.json (default: a temp dir)")
    ap.add_argument("--docs", action="store_true", help="also write docs/images/web_*_demo.png (ratio 2)")
    args = ap.parse_args(argv)
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("error: check.py needs the `websockets` package (pip install websockets)", file=sys.stderr)
        return 2
    if not (HERE / "generated").is_dir():
        print("error: run ./regenerate.sh first", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="ninekit-web-check-"))
    out.mkdir(parents=True, exist_ok=True)
    pieces = load_pieces()
    httpd, port = serve()
    results = []
    try:
        for page in args.pages.split(","):
            for d in [float(v) for v in args.dpr.split(",")]:
                d = int(d) if d.is_integer() else d
                png = out / f"{page}@{d}x.png"
                probes = capture(f"http://127.0.0.1:{port}/{page}.html", d, SIZES[page], png)
                rows = measure(png, probes, d, pieces)
                results.append({"page": page, "dpr": d, "png": str(png), "rows": rows})
                if args.docs and d == 2:
                    dst = ROOT / "docs" / "images" / f"web_{page}_demo.png"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(png, dst)
                    print(f"wrote {dst.relative_to(ROOT)}")
    finally:
        httpd.shutdown()
    (out / "measurements.json").write_text(json.dumps(results, indent=1))
    worst = 0.0
    for res in results:
        print(f"\n{res['page']} @ dpr {res['dpr']}  ({res['png']})")
        for r in res["rows"]:
            cells = [f"{r['probe']:<13}", f"bbox {r['bbox_css']}"]
            for k in ("corner_tl", "corner_br", "whole"):
                if k in r:
                    cells.append(f"{k} max {r[k][0]:>5} mean {r[k][1]:>5}")
                    worst = max(worst, r[k][1])
            if "edge_frac" in r and r["edge_frac"]:
                cells.append(f"(edge off-grid {r['edge_frac']} px)")
            print("  " + "  ".join(cells))
    sizes: dict = {}
    for res in results:
        for r in res["rows"]:
            if r["bbox_css"]:
                sizes.setdefault((res["page"], r["probe"]), []).append(r["bbox_css"][2:])
    spread = {k: max(max(abs(a[i] - b[i]) for a in v for b in v) for i in (0, 1)) for k, v in sizes.items()}
    far = max(spread, key=spread.get) if spread else None
    print(f"\nworst mean corner difference: {worst:.2f} levels; largest drawn-size spread across ratios: "
          f"{spread.get(far, 0):.2f} CSS px ({far}); screenshots in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
