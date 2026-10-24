"""Turn recorded frames into per-scene 1080p30 clips (AI waits time-lapsed), plus contact sheets for review."""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()


def mapper(meta):
    """Map wall-clock time to edited scene time (cut intervals compressed to `keep` seconds)."""
    t0 = meta["t0"]
    cuts = sorted(meta["cuts"])

    def f(t):
        out, last = 0.0, t0
        for a, b, keep in cuts:
            if t <= a:
                break
            out += a - last
            if t < b:
                return out + (t - a) * keep / (b - a)
            out += keep
            last = b
        return out + (t - last)
    return f


def build(name):
    d = ROOT / "scenes" / name
    meta = json.load(open(d / "meta.json"))
    f = mapper(meta)
    times = meta["times"]
    frames = sorted((d / "f").glob("*.jpg"))
    end = f(meta["t1"])
    lines = ["ffconcat version 1.0"]
    pts = [max(0.0, f(t)) for t in times]
    pts[0] = 0.0
    for i, fr in enumerate(frames):
        nxt = pts[i + 1] if i + 1 < len(pts) else end
        dur = max(nxt - pts[i], 0.0)
        if dur <= 0 and i + 1 < len(pts):
            continue
        lines += [f"file 'f/{fr.name}'", f"duration {dur:.4f}"]
    lines.append(f"file 'f/{frames[-1].name}'")
    (d / "list.txt").write_text("\n".join(lines))
    out = d / "clip.mp4"
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-movflags", "+faststart", "clip.mp4"], cwd=d, check=True)
    marks = {k: round(f(v), 2) for k, v in meta["marks"].items()}
    json.dump({"duration": round(end, 2), "marks": marks}, open(d / "clip.json", "w"), indent=1)
    # contact sheet: 12 stills across the clip
    n = 12
    step = max(end / n, 0.1)
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "clip.mp4", "-vf", f"fps=1/{step:.3f},scale=480:-1,tile=4x3", "-frames:v", "1", "sheet.jpg"], cwd=d, check=True)
    print(f"{name}: {end:.1f}s edited (raw {meta['t1'] - meta['t0']:.1f}s), marks {marks}")


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.name for p in (ROOT / "scenes").iterdir() if p.is_dir())
    for n in names:
        build(n)
