"""Generate narration clips (edge-tts neural voice) and measure their durations."""
import asyncio, json, re, subprocess
from pathlib import Path
import edge_tts, imageio_ffmpeg
ROOT = Path(__file__).parent; FF = imageio_ffmpeg.get_ffmpeg_exe()
cfg = json.load(open(ROOT / "narration.json", encoding="utf-8"))
(ROOT / "audio").mkdir(exist_ok=True)
def dur(p):
    e = subprocess.run([FF, "-i", str(p), "-f", "null", "-"], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", e).groups(); return int(h) * 3600 + int(m) * 60 + float(s)
async def main():
    out = {}
    for s in cfg["segments"]:
        mp3 = ROOT / "audio" / f"{s['id']}.mp3"; wav = mp3.with_suffix(".wav")
        for attempt in range(5):
            try:
                await edge_tts.Communicate(s["text"], cfg["voice"], rate=cfg["rate"]).save(str(mp3)); break
            except Exception as e:
                print("retry", s["id"], type(e).__name__); await asyncio.sleep(2 + 3 * attempt)
        else:
            raise SystemExit("TTS failed for " + s["id"])
        # trim leading/trailing silence, 48 kHz stereo wav
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(mp3), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "2", str(wav)], check=True)
        out[s["id"]] = round(dur(wav), 2)
    json.dump(out, open(ROOT / "audio" / "durations.json", "w"), indent=1)
    print(out, "total", round(sum(out.values()), 1), "words", sum(len(s["text"].split()) for s in cfg["segments"]))
asyncio.run(main())
