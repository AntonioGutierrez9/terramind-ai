"""Assemble the final walkthrough: scene clips (gentle speed-ups / holds), crossfades, narration placed at real
on-screen moments, loudness-normalized audio, H.264 1080p30 MP4 + SRT subtitles."""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "terramind_demo.mp4"
X = 0.5      # crossfade seconds
LEAD = 0.4   # narration starts this long after its group begins
GAP = 0.25   # minimum pause between narration clips
TAIL = 0.45  # narration must end this long before its group ends

# scene, speed, group
SCENES = [
    ("s00_title", 1.0, "g1"), ("s01_intro", 1.0, "g1"),
    ("s02_create", 1.11, "g2"),
    ("s03_property", 1.15, "g3"),
    ("s04_model", 1.25, "g4"), ("s04b_excel", 1.12, "g4"),
    ("s05_chat", 1.1, "g5"),
    ("s06_voice_lang", 1.0, "g6"),
    ("s07_sust_ic", 1.15, "g7"),
    ("s08_portfolio_accounts", 1.05, "g8"),
    ("s09_outro_app", 1.0, "g9"), ("s10_end", 1.0, "g9"),
]
GROUP_OF_NARR = {"n1_intro": "g1", "n2_create": "g2", "n3_property": "g3", "n4_model": "g4", "n5a_chat": "g5", "n5b_chat": "g5",
                 "n5c_chat": "g5", "n6_voice": "g6", "n7_sust": "g7", "n8_portfolio": "g8", "n9_end": "g9"}

narr = json.load(open(ROOT / "narration.json", encoding="utf-8"))["segments"]
adur = json.load(open(ROOT / "audio" / "durations.json"))
clips = {n: json.load(open(ROOT / "scenes" / n / "clip.json")) for n, _, _ in SCENES}
pad = {n: 0.0 for n, _, _ in SCENES}


def layout():
    lens = {n: clips[n]["duration"] / s + pad[n] for n, s, _ in SCENES}
    starts, t = {}, 0.0
    for i, (n, _, _) in enumerate(SCENES):
        starts[n] = t
        t += lens[n] - X
    total = t + X
    gstart, gend = {}, {}
    for n, _, g in SCENES:
        gstart.setdefault(g, starts[n])
        gend[g] = starts[n] + lens[n]
    place, prev_end = [], 0.0
    for seg in narr:
        g = GROUP_OF_NARR[seg["id"]]
        scene = seg["scene"]
        speed = dict((n, s) for n, s, _ in SCENES)[scene]
        t0 = gstart[g] + LEAD
        if seg.get("mark"):
            t0 = starts[scene] + clips[scene]["marks"][seg["mark"]] / speed + 0.3
        t0 = max(t0, prev_end + GAP)
        place.append((seg, t0, t0 + adur[seg["id"]], g))
        prev_end = t0 + adur[seg["id"]]
    return lens, starts, total, gend, place


for _ in range(20):  # extend the last scene of a group (frame hold) until its narration fits
    lens, starts, total, gend, place = layout()
    changed = False
    for seg, a, b, g in place:
        if b > gend[g] - TAIL:
            last = [n for n, _, gg in SCENES if gg == g][-1]
            pad[last] += round(b - (gend[g] - TAIL) + 0.05, 2)
            changed = True
            break
    if not changed:
        break
lens, starts, total, gend, place = layout()

print(f"total {total:.1f}s ({int(total // 60)}:{total % 60:04.1f})")
for n, s, g in SCENES:
    print(f"  {n:24s} start {starts[n]:6.1f}  len {lens[n]:5.1f}  speed {s}  hold {pad[n]:.2f}")
for seg, a, b, g in place:
    print(f"  {seg['id']:14s} {a:6.1f} -> {b:6.1f}")

# ---------------------------------------------------------------- ffmpeg graph
inputs, fc = [], []
for i, (n, s, _) in enumerate(SCENES):
    inputs += ["-i", str(ROOT / "scenes" / n / "clip.mp4")]
    hold = f",tpad=stop_mode=clone:stop_duration={pad[n]:.3f}" if pad[n] > 0 else ""
    fc.append(f"[{i}:v]setpts=PTS/{s},fps=30{hold},settb=AVTB,format=yuv420p[v{i}]")
cur, acc = "v0", lens[SCENES[0][0]]
for i in range(1, len(SCENES)):
    off = acc - X
    fc.append(f"[{cur}][v{i}]xfade=transition=fade:duration={X}:offset={off:.3f}[x{i}]")
    cur = f"x{i}"
    acc = off + lens[SCENES[i][0]]
fc.append(f"[{cur}]scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p[vout]")
cur = "vout"
base = len(SCENES)
for k, (seg, a, b, g) in enumerate(place):
    inputs += ["-i", str(ROOT / "audio" / f"{seg['id']}.wav")]
    ms = int(round(a * 1000))
    fc.append(f"[{base + k}:a]adelay={ms}|{ms}[a{k}]")
fc.append("".join(f"[a{k}]" for k in range(len(place))) + f"amix=inputs={len(place)}:normalize=0,apad,atrim=0:{total:.3f},"
          "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
cmd = [FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", "30",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(OUT)]
subprocess.run(cmd, check=True)

# ---------------------------------------------------------------- subtitles (narration split into short cues)
def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


cues = []
for seg, a, b, g in place:
    parts = [p.strip() for p in re.split(r"(?<=[.,;])\s+", seg["text"]) if p.strip()]
    chunks, buf = [], ""
    for p in parts:
        if len((buf + " " + p).split()) > 14 and buf:
            chunks.append(buf.strip())
            buf = p
        else:
            buf = (buf + " " + p).strip()
    if buf:
        chunks.append(buf)
    words = sum(len(c.split()) for c in chunks)
    t = a
    for c in chunks:
        d = (b - a) * len(c.split()) / words
        cues.append((t, t + d, c))
        t += d
srt = "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n" for i, (a, b, txt) in enumerate(cues, 1))
OUT.with_suffix(".srt").write_text(srt, encoding="utf-8")
json.dump({"total": total, "scenes": {n: {"start": starts[n], "len": lens[n]} for n, _, _ in SCENES},
           "narration": [{"id": s["id"], "start": a, "end": b, "text": s["text"]} for s, a, b, _ in place]},
          open(ROOT / "timeline.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")
