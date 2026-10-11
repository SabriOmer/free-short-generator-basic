"""
Shorts bot (cok nisli, cok dilli) - hafif surum (zayif laptoplar icin)
Gemini (senaryo) + edge-tts (ses + kelime zamani) + Pexels (gorsel) + FFmpeg (montaj)

Kullanim:  python shorts_bot.py "konu"
Gerekli:   pip install edge-tts requests   |  FFmpeg PATH'te olmali
Ortam:     NICHE (phones/facts/motivation/finance/gaming/space/fitness), LANG_CODE (en/tr)
Ortam:     GEMINI_API_KEY, PEXELS_API_KEY (Pexels yoksa Pollinations kullanilir)
"""
import asyncio, base64, json, os, random, re, shutil, subprocess, sys, time, wave
from pathlib import Path
import requests
try:
    import edge_tts
except ImportError:  # edge-tts yoksa yedek motorlar kullanilir
    edge_tts = None

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACKS = ["gemini-2.5-flash", "gemini-2.0-flash"]
W, H = 720, 1280
N_IMAGES = 5
FADE = 0.4

# --- NIS AYARLARI: yeni nis eklemek icin buraya bir satir ekle ---
# ad: (kanal konusu, gorsel arama kurali, Pixabay kategorisi)
NICHES = {
    "phones": ("smartphones and mobile operating systems (iOS, Android, One UI, HyperOS, etc)",
               'MUST contain the word "smartphone" or "phone", e.g. "hand holding smartphone", "smartphone screen closeup", "person using phone"',
               "computer"),
    "facts": ("surprising, verified science, nature and history facts",
              'concrete visual scenes of the subject, e.g. "deep ocean waves", "ancient ruins sunset", "night sky stars"',
              ""),
    "motivation": ("motivation, discipline and self-improvement habits",
                   'concrete visual scenes, e.g. "man running sunrise", "person writing notebook", "mountain climbing silhouette"',
                   "people"),
    "finance": ("personal finance, saving and investing basics (educational, not financial advice)",
                'concrete visual scenes, e.g. "coins stack growing", "person calculating budget", "city skyline business"',
                "business"),
    "gaming": ("video games, tips and gaming tech",
               'concrete visual scenes, e.g. "gaming setup neon", "hands holding controller", "gaming keyboard closeup"',
               "computer"),
    "space": ("space, planets and astronomy",
              'concrete visual scenes, e.g. "galaxy stars nebula", "planet surface", "rocket launch"',
              "science"),
    "fitness": ("fitness, workouts and healthy habits",
                'concrete visual scenes, e.g. "man lifting weights", "woman running outdoors", "healthy meal prep"',
                "sports"),
}
NICHE = os.getenv("NICHE", "phones")
if NICHE not in NICHES:
    sys.exit(f"Bilinmeyen nis: {NICHE}. Secenekler: {', '.join(NICHES)}")
NICHE_DESC, KW_RULE, PIX_CAT = NICHES[NICHE]

# dil: (dil adi, edge-tts sesi)
LANGS = {"en": ("English", "en-US-GuyNeural"), "tr": ("Turkish", "tr-TR-AhmetNeural")}
LANG = os.getenv("LANG_CODE", "en")
if LANG not in LANGS:
    sys.exit(f"Bilinmeyen dil: {LANG}. Secenekler: {', '.join(LANGS)}")
LANG_NAME, DEFAULT_VOICE = LANGS[LANG]
VOICE = os.getenv("TTS_VOICE", DEFAULT_VOICE)

PROMPT = """You write YouTube Shorts for a {lang} channel about {niche}.
Topic: "{topic}"
Rules:
- Write the voiceover in {lang}. Length: 75-85 words, fast-paced, strong hook in the first sentence, ends with a short question or call to follow.
- Only include well-established facts. Never present rumors, guesses or unverified claims as facts. If unsure, leave the claim out.
- No emojis, no stage directions, plain spoken text.
Return JSON with keys:
"title" (under 70 chars, catchy, in {lang}), "script" (the narration in {lang}), "keywords" (list of 5 stock-photo search queries IN ENGLISH, 2-4 words each, concrete and visual, all sharing one consistent visual theme and style; each {kw_rule}), "hashtags" (list of 4 hashtags without #, in {lang})."""


def up(w):
    """Buyuk harf (Turkce i/I duzeltmesiyle)."""
    if LANG == "tr":
        w = w.replace("i", "İ").replace("ı", "I")
    return w.upper()


def gemini(topic):
    if not GEMINI_KEY:
        sys.exit("GEMINI_API_KEY ayarli degil.")
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(topic=topic, lang=LANG_NAME, niche=NICHE_DESC, kw_rule=KW_RULE)}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    models = [MODEL] + [m for m in FALLBACKS if m != MODEL]
    txt = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        for attempt in range(4):
            r = requests.post(url, json=body, timeout=90)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"   Model: {model}")
                break
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 5 * (attempt + 1)
                print(f"   {model} mesgul ({r.status_code}), {wait} sn sonra tekrar...")
                time.sleep(wait)
                continue
            print(f"   {model} kullanilamadi ({r.status_code}), siradaki model...")
            break
        if txt:
            break
    if not txt:
        sys.exit("Hicbir Gemini modeli yanit vermedi. Biraz sonra tekrar dene.")
    data = json.loads(txt)
    data["script"] = re.sub(r"\s+", " ", data["script"]).strip()
    return data


async def tts(text, mp3_path):
    com = edge_tts.Communicate(text, VOICE, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["text"], ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7))
    return words


# ---------------- SES: edge-tts bozulursa yedek motorlar ----------------
TTS_ENGINE = os.getenv("TTS_ENGINE", "auto")  # auto | edge | gemini | windows
TTS_MODELS = [m for m in [os.getenv("TTS_MODEL"), "gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"] if m]
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Puck")  # ornek: Puck, Kore, Charon, Zephyr, Fenrir
TTS_STYLE = os.getenv("TTS_STYLE", "Say in a fast, energetic, engaging YouTube Shorts narrator voice")


def silence_spans(audio, duration):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(audio), "-af", "silencedetect=noise=-35dB:d=0.18", "-f", "null", "-"],
                       capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(max(0.0, a), en[i] if i < len(en) else duration) for i, a in enumerate(st)]


def estimate_words(text, duration, audio=None, lead=0.15, tail=0.25):
    """Kelime zamani vermeyen motorlar icin tahmin. Ses dosyasi verilirse gercek
    sessizliklere (cumle/virgul aralari) hizalar, bu da altyazi kaymasini azaltir."""
    toks = text.split()
    if not toks:
        return []
    letter = [len(re.sub(r"\W", "", w)) + 1.5 for w in toks]
    punct = [w.endswith((".", "!", "?", ",", ";", ":")) for w in toks]
    bonus = [(4 if w.endswith((".", "!", "?")) else 2) if punct[i] else 0 for i, w in enumerate(toks)]
    t0, t1 = lead, max(lead + 0.5, duration - tail)
    matched = {}
    if audio is not None:
        try:
            sil = silence_spans(audio, duration)
            if sil and sil[0][0] < 0.08:
                t0 = sil[0][1]
                sil = sil[1:]
            if sil and sil[-1][1] > duration - 0.08:
                t1 = sil[-1][0]
                sil = sil[:-1]
            wts = [l + b for l, b in zip(letter, bonus)]
            tot, acc, ends = sum(wts) or 1, 0, []
            for x in wts:
                acc += x
                ends.append(t0 + (t1 - t0) * acc / tot)
            last = -1
            for s0, e0 in sil:
                mid = (s0 + e0) / 2
                cands = [i for i in range(last + 1, len(toks) - 1) if punct[i]]
                if not cands:
                    break
                i = min(cands, key=lambda k: abs(ends[k] - mid))
                if abs(ends[i] - mid) < 2.0:
                    matched[i] = (s0, e0)
                    last = i
        except Exception:
            matched = {}
            t0, t1 = lead, max(lead + 0.5, duration - tail)
    out, start, cur = [], 0, t0
    for c in sorted(matched) + [len(toks) - 1]:
        idxs = list(range(start, c + 1))
        seg_end = matched[c][0] if c in matched else t1
        if seg_end <= cur + 0.05:
            seg_end = cur + 0.05 * len(idxs)
        ws = [letter[i] + (bonus[i] if i != c else 0) for i in idxs]
        tot, t = sum(ws) or 1, cur
        for i, x in zip(idxs, ws):
            d = (seg_end - cur) * x / tot
            out.append((toks[i], t, t + d))
            t += d
        cur = matched[c][1] if c in matched else seg_end
        start = c + 1
    return out


def pcm_to_mp3(pcm, mp3_path, rate=24000):
    wav = Path(str(mp3_path) + ".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "3", str(mp3_path)], check=True)
    wav.unlink(missing_ok=True)
    return len(pcm) / 2 / rate


def gemini_tts(text, mp3_path):
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY yok")
    body = {
        "contents": [{"parts": [{"text": f"{TTS_STYLE}: {text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE}}},
        },
    }
    last = "bilinmeyen hata"
    for model in TTS_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        for attempt in range(3):
            r = requests.post(url, json=body, timeout=120)
            if r.status_code == 200:
                try:
                    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                    pcm = base64.b64decode(part["data"])
                    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
                    dur = pcm_to_mp3(pcm, mp3_path, int(m.group(1)) if m else 24000)
                    print(f"   Ses: Gemini TTS ({model}, {GEMINI_VOICE})")
                    return estimate_words(text, dur, mp3_path)
                except (KeyError, IndexError):
                    last = f"{model}: ses verisi gelmedi"
                    break
            last = f"{model}: HTTP {r.status_code} {r.text[:150]}"
            if r.status_code in (429, 500, 503):
                time.sleep(4 * (attempt + 1))
                continue
            break
    raise RuntimeError(last)


def windows_tts(text, mp3_path):
    """Windows'un kendi sesi (internetsiz). Kalite dusuk, son care."""
    txt = Path(str(mp3_path) + ".txt")
    wav = Path(str(mp3_path) + ".wav")
    txt.write_text(text, encoding="utf-8")
    prefix = "tr" if LANG == "tr" else "en"
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$v=$s.GetInstalledVoices()|Where-Object {{$_.VoiceInfo.Culture.Name -like '{prefix}*'}}|Select-Object -First 1;"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        f"$s.SetOutputToWaveFile('{wav}');"
        f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{txt}'));$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "3", str(mp3_path)], check=True)
    dur = probe_duration(mp3_path)
    txt.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    print("   Ses: Windows sesi (yedek)")
    return estimate_words(text, dur, mp3_path)


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def speak(text, mp3_path):
    """Sirayla dener: edge-tts -> Gemini TTS -> Windows sesi. Kelime zamanlarini dondurur."""
    order = {"auto": ["edge", "gemini", "windows"], "edge": ["edge"], "gemini": ["gemini"], "windows": ["windows"]}.get(TTS_ENGINE, ["edge", "gemini", "windows"])
    errs = []
    for eng in order:
        try:
            if eng == "edge":
                if edge_tts is None:
                    raise RuntimeError("edge-tts kurulu degil")
                words = asyncio.run(tts(text, mp3_path))
                if not words:
                    raise RuntimeError("kelime zamani gelmedi")
                print("   Ses: edge-tts")
                return words
            if eng == "gemini":
                return gemini_tts(text, mp3_path)
            return windows_tts(text, mp3_path)
        except Exception as e:
            msg = f"{eng}: {type(e).__name__}: {str(e)[:120]}"
            errs.append(msg)
            print("   Ses motoru calismadi ->", msg)
    sys.exit("Hicbir ses motoru calismadi:\n  " + "\n  ".join(errs))


def download(url, path):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    Path(path).write_bytes(r.content)


def get_images(keywords, topic, outdir):
    """Oncelik: my_images klasoru > Pixabay > Pexels > Pollinations. Eksikse eldekiler tekrar kullanilir."""
    paths = []
    # 1) Kendi gorsellerin (ekran goruntusu vb.)
    mine = Path("my_images")
    if mine.exists():
        files = [f for f in mine.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        random.shuffle(files)
        for f in files[:N_IMAGES]:
            name = f"img{len(paths)}{f.suffix.lower()}"
            shutil.copy(f, outdir / name)
            paths.append(name)
        print(f"my_images: {len(paths)} gorsel kullanildi")
    poll_ok = True
    for i in range(len(paths), N_IMAGES):
        q = keywords[i % len(keywords)]
        p = outdir / f"img{i}.jpg"
        ok = False
        if PIXABAY_KEY:
            try:
                r = requests.get(
                    "https://pixabay.com/api/",
                    params={"key": PIXABAY_KEY, "q": q, "image_type": "photo", "orientation": "vertical",
                            **({"category": PIX_CAT} if PIX_CAT else {}), "per_page": 20, "safesearch": "true"},
                    timeout=30,
                )
                hits = r.json().get("hits", [])
                if not hits:  # kategori cok daraltirsa kategorisiz tekrar dene
                    r = requests.get(
                        "https://pixabay.com/api/",
                        params={"key": PIXABAY_KEY, "q": q,
                                "image_type": "photo", "orientation": "vertical", "per_page": 20, "safesearch": "true"},
                        timeout=30,
                    )
                    hits = r.json().get("hits", [])
                if hits:
                    download(random.choice(hits[:10])["largeImageURL"], p)
                    ok = True
            except Exception as e:
                print("Pixabay hata:", e)
        if not ok and PEXELS_KEY:
            try:
                r = requests.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": PEXELS_KEY},
                    params={"query": q, "orientation": "portrait", "per_page": 8},
                    timeout=30,
                )
                photos = r.json().get("photos", [])
                if photos:
                    download(random.choice(photos)["src"]["portrait"], p)
                    ok = True
            except Exception as e:
                print("Pexels hata:", e)
        if not ok and poll_ok:
            try:
                u = f"https://image.pollinations.ai/prompt/{requests.utils.quote(q + ', vertical, no text')}?width=720&height=1280&nologo=true&seed={random.randint(1,99999)}"
                download(u, p)
                ok = True
            except Exception as e:
                print("Pollinations kullanilamiyor, atlaniyor:", e)
                poll_ok = False
        if ok:
            paths.append(p.name)
        print(f"gorsel {i + 1}/{N_IMAGES}", "ok" if ok else "yok")
    if not paths:
        sys.exit("Hic gorsel yok. my_images klasorune birkac resim koy ya da PIXABAY_API_KEY ayarla.")
    if len(paths) < N_IMAGES:
        print(f"Uyari: sadece {len(paths)} farkli gorsel var, tekrar kullanilacak.")
        paths = (paths * N_IMAGES)[:N_IMAGES]
    return paths


def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_ass(words, path, chunk=3):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,7,0,2,40,40,330,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []
    clean = [(up(re.sub(r"[{}\\]", "", w)), s, e) for w, s, e in words]
    for ci in range(0, len(clean), chunk):
        grp = clean[ci:ci + chunk]
        for k, (w, s, e) in enumerate(grp):
            end = clean[ci + k + 1][1] if ci + k + 1 < len(clean) else e + 0.3
            parts = []
            for j, (w2, _, _) in enumerate(grp):
                if j == k:
                    parts.append("{\\c&H00E6FF&}" + w2 + "{\\c&HFFFFFF&}")  # sari (BGR)
                else:
                    parts.append(w2)
            lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(end)},Default,,0,0,0,,{' '.join(parts)}")
    Path(path).write_text(head + "\n".join(lines), encoding="utf-8")


def make_video(outdir, imgs, total):
    n = len(imgs)
    L = (total + (n - 1) * FADE) / n
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats"]
    for im in imgs:
        cmd += ["-i", im]
    cmd += ["-i", "voice.mp3"]
    f = []
    for i in range(n):
        D = max(2, int(L * 25))
        z = f"1+0.12*on/{D}" if i % 2 == 0 else f"1.12-0.12*on/{D}"
        f.append(f"[{i}:v]scale=900:1600:force_original_aspect_ratio=increase,crop=900:1600,"
                 f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={D}:s={W}x{H}:fps=25,"
                 f"setsar=1,format=yuv420p[v{i}]")
    prev = "v0"
    for i in range(1, n):
        out = f"x{i}"
        f.append(f"[{prev}][v{i}]xfade=transition=fade:duration={FADE}:offset={i * (L - FADE):.3f}[{out}]")
        prev = out
    f.append(f"[{prev}]ass=subs.ass[vout]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", f"{n}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.3f}", "-movflags", "+faststart", "short.mp4"]
    subprocess.run(cmd, cwd=outdir, check=True)


def main():
    if len(sys.argv) < 2:
        sys.exit('Kullanim: python shorts_bot.py "konu"')
    topic = " ".join(sys.argv[1:])
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    outdir = Path("output") / slug
    outdir.mkdir(parents=True, exist_ok=True)

    print("1/4 Senaryo...")
    data = gemini(topic)
    print("   Baslik:", data["title"])

    print("2/4 Ses...")
    words = speak(data["script"], outdir / "voice.mp3")
    total = words[-1][2] + 0.6
    write_ass(words, outdir / "subs.ass")

    print("3/4 Gorseller...")
    imgs = get_images(data["keywords"], topic, outdir)

    print("4/4 Montaj...")
    make_video(outdir, imgs, total)

    tags = " ".join("#" + t.strip("# ") for t in data.get("hashtags", [])) + " #shorts"
    (outdir / "meta.txt").write_text(f"{data['title']}\n\n{data['script']}\n\n{tags}\n", encoding="utf-8")
    print(f"\nHazir: {outdir / 'short.mp4'}\nBaslik/aciklama: {outdir / 'meta.txt'}")


if __name__ == "__main__":
    main()
