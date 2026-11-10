#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["kokoro-onnx", "soundfile"]
# ///
"""Build a narrated briefing from one slides file.

    uv run present.py <name>.slides.html [--voice heart|harper] [--mp4]

Reads <name>.slides.html, narrates each slide, and writes <name>.html: one self-contained page
holding the slides, the audio and the player. It opens in any browser and in harness previews that
show HTML; nothing has to be running.

A slides file is plain HTML. Each <section class="slide" data-title="..."> is one slide and the
<aside class="say"> right after it is what is spoken. data-hold lingers on a dense slide;
data-decision marks a slide that asks for a decision.

Voices: george (default) and heart are local. The voice model, about 350 MB, is downloaded once per
machine. harper is Azure speech and needs credentials: AZURE_VOICE_KEY and AZURE_VOICE_REGION (or
the other names in AZURE_NAMES below), from the environment, the project's .env or WORK/.env.
Narration is cached per voice and text, so only changed slides are spoken again.

--mp4 also writes <name>.mp4 for sharing: the slides as pictures, the same narration, a chapter per
slide and captions. It needs Google Chrome or Chromium to draw the slides.

Needs: ffmpeg on the path; kokoro-onnx and soundfile, which uv installs from the header above.
"""
import argparse, base64, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, urllib.error, urllib.request, wave
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get('TRESSOIR_CACHE') or Path.home() / '.cache' / 'tressoir')
MODEL_URL = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
LOCAL_VOICES = {'george': ('bm_george', 'en-gb'), 'heart': ('af_heart', 'en-us')}
HARPER = ('en-US-Harper:MAI-Voice-2.1', 'audiobook')
# Where Azure credentials are looked for, in order: (region variable, key variable, fixed region).
AZURE_NAMES = [('AZURE_VOICE_REGION', 'AZURE_VOICE_KEY', ''), ('AZURE_SPEECH_REGION', 'AZURE_SPEECH_KEY', ''),
               ('', 'US_EAST2_AZURE_API_KEY', 'eastus2'), ('', 'US_EAST_AZURE_API_KEY', 'eastus')]
RATE = 24000                                           # both the local voices and Azure give 24 kHz mono
GAP, HOLD_EXTRA, DECISION_EXTRA = 0.45, 3.0, 1.5       # seconds of silence after a slide's narration
LIMIT = 1_800_000                                      # inline previews refuse files over about 2 MB
CHROME_PLACES = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
                 '~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
CHROME_NAMES = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome']

SLIDE = re.compile(r'<section\s+class="slide"([^>]*)>(.*?)</section>\s*<aside\s+class="say">(.*?)</aside>', re.S)


def read_slides(path: Path):
    text = path.read_text(encoding='utf-8')
    title = re.search(r'<title>(.*?)</title>', text, re.S)
    styles = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', text.split('<body', 1)[0], re.S))
    slides = []
    for attrs, body, say in SLIDE.findall(text):
        name = re.search(r'data-title="([^"]*)"', attrs)
        spoken = html.unescape(re.sub(r'<[^>]+>', '', say)).strip()
        spoken = re.sub(r'\s+', ' ', spoken)
        slide = {'title': html.unescape(name.group(1)) if name else f'Slide {len(slides) + 1}', 'html': body.strip(), 'say': spoken}
        if 'data-hold' in attrs: slide['hold'] = True
        if 'data-decision' in attrs: slide['decision'] = True
        slides.append(slide)
    if not slides:
        sys.exit(f'No slides found in {path.name}. Each slide is a <section class="slide"> followed by an <aside class="say">.')
    silent = [s['title'] for s in slides if not s['say']]
    if silent:
        sys.exit('These slides have no narration: ' + ', '.join(silent))
    return (html.unescape(title.group(1).strip()) if title else path.stem), styles, slides


def find_chrome():
    named = os.environ.get('CHROME')
    if named:
        return named if Path(named).exists() or shutil.which(named) else None
    for place in CHROME_PLACES:
        if Path(place).expanduser().exists(): return str(Path(place).expanduser())
    for name in CHROME_NAMES:
        if shutil.which(name): return shutil.which(name)
    return None


def check_tools(mp4: bool):
    """Stop before any work if something this run needs is not installed, naming all of it."""
    missing = []
    if not shutil.which('ffmpeg'):
        missing.append('ffmpeg, which compresses the narration. Install it, for example: brew install ffmpeg')
    chrome = find_chrome() if mp4 else None
    if mp4 and not chrome:
        missing.append('Google Chrome or Chromium, which draws the slides for --mp4. Install one, or set CHROME to its path')
    if missing:
        sys.exit('Cannot build. Missing:\n' + '\n'.join('  - ' + m for m in missing))
    return chrome


def narrate(slides, voice, src: Path):
    """One WAV per slide, from the cache when the same voice has already spoken the same text."""
    store = CACHE / 'narration'; store.mkdir(parents=True, exist_ok=True)
    speak = None; paths = []; made = 0
    for slide in slides:
        wav = store / f"{voice}-{hashlib.sha256(slide['say'].encode()).hexdigest()[:20]}.wav"
        if not wav.exists():
            if speak is None:
                speak = harper_voice(src) if voice == 'harper' else local_voice(voice)
            part = wav.with_suffix('.part.wav'); speak(slide['say'], part); part.rename(wav)
            made += 1
        paths.append(wav)
    return paths, made


def local_voice(voice):
    try:
        from kokoro_onnx import Kokoro
        import soundfile
    except ImportError:
        sys.exit('The local voice is not installed. Run this script through uv:\n  uv run present.py <file>')
    folder = CACHE / 'kokoro'; folder.mkdir(parents=True, exist_ok=True)
    for name in ('kokoro-v1.0.onnx', 'voices-v1.0.bin'):
        if not (folder / name).exists():
            print(f'Downloading the voice model file {name} (once per machine) ...', file=sys.stderr, flush=True)
            part = folder / (name + '.part'); urllib.request.urlretrieve(MODEL_URL + name, part); part.rename(folder / name)
    model = Kokoro(str(folder / 'kokoro-v1.0.onnx'), str(folder / 'voices-v1.0.bin'))
    name, lang = LOCAL_VOICES[voice]

    def speak(text, out: Path):
        samples, rate = model.create(text, voice=name, lang=lang)
        soundfile.write(out, samples, rate, subtype='PCM_16')
    return speak


def project_root(start: Path):
    for folder in [start, *start.parents]:
        if (folder / '.git').exists(): return folder
    return start


def azure_credentials(src: Path):
    """The environment first, then .env at the project root and in its work area. Nowhere else."""
    root = project_root(src.resolve().parent)
    places = [root / '.env', root / 'WORK' / '.env']
    found = dict(os.environ)
    for place in places:
        if not place.is_file(): continue
        for line in place.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line.startswith('export '): line = line[7:]
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                found.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for region_name, key_name, fixed in AZURE_NAMES:
        if found.get(key_name) and (fixed or found.get(region_name)):
            return found[key_name], fixed or found[region_name]
    sys.exit('The Harper voice needs Azure speech credentials and none were found.\n'
             f'Looked in the environment, {places[0]} and {places[1]}.\n'
             'Ask the user for AZURE_VOICE_KEY and AZURE_VOICE_REGION. Do not look for them in other projects.')


def harper_voice(src: Path):
    key, region = azure_credentials(src)
    name, style = HARPER

    def speak(text, out: Path):
        ssml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">'
                f'<voice name="{name}"><mstts:express-as style="{style}">{escape(text)}</mstts:express-as></voice></speak>')
        req = urllib.request.Request(f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1', data=ssml.encode(), method='POST',
                                     headers={'Ocp-Apim-Subscription-Key': key, 'Content-Type': 'application/ssml+xml',
                                              'X-Microsoft-OutputFormat': 'raw-24khz-16bit-mono-pcm', 'User-Agent': 'tressoir-present'})
        try:
            with urllib.request.urlopen(req, timeout=120) as r: pcm = r.read()
        except urllib.error.HTTPError as e:
            sys.exit(f'Azure speech refused the request (HTTP {e.code}, region {region}). Check the key and region with the user.')
        except urllib.error.URLError as e:
            sys.exit(f'Azure speech could not be reached: {e.reason}')
        if len(pcm) < 2000: sys.exit('Azure speech returned no audio.')
        with wave.open(str(out), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return speak


def build_track(slides, wavs, work: Path):
    """Join the slide narrations into one track with pauses. Returns each slide's start time,
    how long its narration lasts, and the total length; writes track.wav and track.webm."""
    with wave.open(str(wavs[0])) as first: params = first.getparams()
    cues, spoken, t = [], [], 0.0
    with wave.open(str(work / 'track.wav'), 'wb') as out:
        out.setparams(params)
        for slide, path in zip(slides, wavs):
            cues.append(round(t, 3))
            with wave.open(str(path)) as w:
                frames = w.getnframes(); out.writeframes(w.readframes(frames))
            pause = GAP + (HOLD_EXTRA if slide.get('hold') else 0) + (DECISION_EXTRA if slide.get('decision') else 0)
            out.writeframes(b'\0' * (int(pause * params.framerate) * params.sampwidth * params.nchannels))
            spoken.append(frames / params.framerate)
            t += frames / params.framerate + pause
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(work / 'track.wav'), '-c:a', 'libopus', '-b:a', '22k',
                    '-ac', '1', '-application', 'voip', str(work / 'track.webm')], check=True)
    return cues, spoken, t


def page_styles():
    return (HERE / 'slides.css').read_text(encoding='utf-8') + '\n' + (HERE / 'player' / 'player.css').read_text(encoding='utf-8')


def bundle(title, deck_styles, slides, cues, track):
    player = (HERE / 'player' / 'player.js').read_text(encoding='utf-8')
    data = json.dumps(slides, ensure_ascii=False).replace('</', '<\\/')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{page_styles()}
{deck_styles}
</style></head>
<body><main>
<div id="deck"></div>
<p class="diag" id="diag" hidden></p>
</main>
<script>
const TITLE = {json.dumps(title)}, SLIDES = {data}, CUES = {json.dumps(cues)};
const TRACK = "{track}";
{player}
</script></body></html>
'''


def stamp(x):
    h, r = divmod(x, 3600); m, s = divmod(r, 60)
    return f'{int(h):02d}:{int(m):02d}:{s:06.3f}'.replace('.', ',')


def export_mp4(chrome, title, deck_styles, slides, cues, spoken, total, work: Path, out: Path):
    """Draw each slide with headless Chrome (light colours, 1920 x 1080) and join the pictures with
    the narration. Chapters carry the slide titles; captions are timed by sentence length."""
    profile = work / 'chrome'; ends = cues[1:] + [total]
    for k, slide in enumerate(slides):
        page = work / f'slide{k:02d}.html'
        page.write_text(f'''<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><style>
{page_styles()}
{deck_styles}
html, body {{ background: var(--panel); overflow: hidden; }}
</style></head><body><div class="slide">{slide['html']}</div></body></html>''', encoding='utf-8')
        shot = work / f'slide{k:02d}.png'
        cmd = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
               f'--user-data-dir={profile}', '--force-device-scale-factor=2', '--window-size=960,540', f'--screenshot={shot}', page.as_uri()]
        if hasattr(os, 'geteuid') and os.geteuid() == 0: cmd.insert(1, '--no-sandbox')
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if not shot.exists():
            sys.exit(f'Chrome did not draw slide {k + 1} for the video.\n{done.stderr.strip()[-600:]}')
    (work / 'pictures.txt').write_text(''.join(f"file 'slide{k:02d}.png'\nduration {ends[k] - cues[k]:.3f}\n" for k in range(len(slides)))
                                       + f"file 'slide{len(slides) - 1:02d}.png'\n")
    plain = lambda s: re.sub(r'([=;#\\\n])', r'\\\1', s)
    (work / 'chapters.txt').write_text(f';FFMETADATA1\ntitle={plain(title)}\n' + ''.join(
        f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(cues[k] * 1000)}\nEND={int(ends[k] * 1000)}\ntitle={plain(s["title"])}\n'
        for k, s in enumerate(slides)), encoding='utf-8')
    lines, n = [], 0
    for k, slide in enumerate(slides):
        sentences = re.findall(r'[^.!?]+[.!?]+["\')\]]*\s*', slide['say']) or [slide['say']]
        weight = sum(len(s) for s in sentences); at = cues[k]
        for s in sentences:
            until = at + spoken[k] * len(s) / weight; n += 1
            lines.append(f'{n}\n{stamp(at)} --> {stamp(until)}\n{s.strip()}\n'); at = until
    (work / 'captions.srt').write_text('\n'.join(lines), encoding='utf-8')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(work / 'pictures.txt'),
                    '-i', str(work / 'track.wav'), '-i', str(work / 'chapters.txt'), '-i', str(work / 'captions.srt'),
                    '-map', '0:v', '-map', '1:a', '-map', '3:s', '-map_metadata', '2', '-map_chapters', '2',
                    '-vf', 'fps=2,scale=1920:1080,format=yuv420p', '-c:v', 'libx264', '-tune', 'stillimage', '-crf', '26', '-g', '20',
                    '-c:a', 'aac', '-b:a', '40k', '-ac', '1', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
                    '-movflags', '+faststart', '-t', f'{total:.3f}', str(out)], check=True)


def main():
    ap = argparse.ArgumentParser(description='Build a narrated briefing from a slides file.')
    ap.add_argument('slides', type=Path, help='the <name>.slides.html file')
    ap.add_argument('--voice', choices=[*sorted(LOCAL_VOICES), 'harper'], default='george',
                    help='george (default) and heart are local; harper uses Azure speech')
    ap.add_argument('--mp4', action='store_true', help='also write <name>.mp4, for sharing')
    args = ap.parse_args()
    src = args.slides
    if not src.name.endswith('.slides.html'): sys.exit('The slides file must be named <name>.slides.html')
    if not src.is_file(): sys.exit(f'No such file: {src}')
    chrome = check_tools(args.mp4)
    title, deck_styles, slides = read_slides(src)
    wavs, made = narrate(slides, args.voice, src)
    out = src.with_name(src.name.replace('.slides.html', '.html'))
    report = {'file': str(out), 'slides': len(slides), 'slides_narrated_now': made, 'voice': args.voice}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        cues, spoken, seconds = build_track(slides, wavs, work)
        track = base64.b64encode((work / 'track.webm').read_bytes()).decode()
        out.write_text(bundle(title, deck_styles, slides, cues, track), encoding='utf-8')
        if args.mp4:
            video = out.with_suffix('.mp4')
            export_mp4(chrome, title, deck_styles, slides, cues, spoken, seconds, work, video)
            report.update(mp4=str(video), mp4_kb=round(video.stat().st_size / 1024))
    size = out.stat().st_size
    if size > LIMIT:
        print(f'Warning: {out.name} is {size / 1e6:.1f} MB. Inline previews refuse files over about 2 MB; split the briefing.', file=sys.stderr)
    report.update(seconds=round(seconds), size_kb=round(size / 1024))
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
