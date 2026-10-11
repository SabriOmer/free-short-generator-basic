"""
Shorts Bot - basit arayuz (tkinter, ekstra kurulum yok)
shorts_bot.py ile AYNI klasorde dursun. Calistir:  python shorts_gui.py
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT = HERE / "shorts_bot.py"
q = queue.Queue()
state = {"proc": None, "outdir": None}


def run(topic, niche, lang):
    cmd = [sys.executable, "-u", str(BOT), topic]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NICHE=niche, LANG_CODE=lang)
    try:
        p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", env=env, creationflags=flags)
        state["proc"] = p
        for line in p.stdout:
            q.put(("log", line.rstrip()))
        p.wait()
        q.put(("done", p.returncode))
    except Exception as e:
        q.put(("log", f"Hata: {e}"))
        q.put(("done", 1))


def start():
    topic = topic_var.get().strip()
    if not topic:
        messagebox.showinfo("Konu gerekli", "Once bir video konusu yaz.")
        return
    if not os.getenv("GEMINI_API_KEY"):
        messagebox.showwarning("Key yok", "GEMINI_API_KEY ayarli degil. setx ile ayarlayip bu pencereyi yeniden ac.")
        return
    btn.config(state="disabled", text="Uretiliyor...")
    log.delete("1.0", "end")
    bar.start(12)
    threading.Thread(target=run, args=(topic, niche_var.get(), "tr" if lang_var.get() == "Turkce" else "en"), daemon=True).start()
    poll()


def poll():
    try:
        while True:
            kind, val = q.get_nowait()
            if kind == "log":
                log.insert("end", val + "\n")
                log.see("end")
            else:
                bar.stop()
                btn.config(state="normal", text="Video uret")
                if val == 0:
                    log.insert("end", "\nBITTI. 'Klasoru ac' ile videoyu bulabilirsin.\n")
                    messagebox.showinfo("Hazir", "Video hazir!")
                else:
                    log.insert("end", "\nBir hata olustu, yukaridaki mesaja bak.\n")
                log.see("end")
                return
    except queue.Empty:
        pass
    root.after(150, poll)


def open_out():
    out = HERE / "output"
    out.mkdir(exist_ok=True)
    dirs = sorted([d for d in out.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
    os.startfile(dirs[0] if dirs else out)


def open_imgs():
    d = HERE / "my_images"
    d.mkdir(exist_ok=True)
    os.startfile(d)


root = tk.Tk()
root.title("Shorts Bot")
root.geometry("640x520")
root.configure(bg="#14141c")
pad = {"padx": 14, "pady": 6}

tk.Label(root, text="Video konusu (Ingilizce yazman daha iyi)", bg="#14141c", fg="#cfcfe0").pack(anchor="w", **pad)
topic_var = tk.StringVar(value="Why iPhone feels smoother than Android")
tk.Entry(root, textvariable=topic_var, font=("Segoe UI", 12), bg="#23232f", fg="white",
         insertbackground="white", relief="flat").pack(fill="x", padx=14, ipady=8)

opt = tk.Frame(root, bg="#14141c")
opt.pack(fill="x", padx=14, pady=4)
from tkinter import ttk
tk.Label(opt, text="Nis:", bg="#14141c", fg="#cfcfe0").pack(side="left")
niche_var = tk.StringVar(value="phones")
ttk.Combobox(opt, textvariable=niche_var, state="readonly", width=12,
             values=["phones", "facts", "motivation", "finance", "gaming", "space", "fitness"]).pack(side="left", padx=(6, 18))
tk.Label(opt, text="Dil:", bg="#14141c", fg="#cfcfe0").pack(side="left")
lang_var = tk.StringVar(value="English")
ttk.Combobox(opt, textvariable=lang_var, state="readonly", width=10, values=["English", "Turkce"]).pack(side="left", padx=6)

row = tk.Frame(root, bg="#14141c")
row.pack(fill="x", **pad)
btn = tk.Button(row, text="Video uret", command=start, bg="#0a84ff", fg="white", relief="flat",
                font=("Segoe UI", 11, "bold"), padx=16, pady=8, cursor="hand2")
btn.pack(side="left")
tk.Button(row, text="Klasoru ac", command=open_out, bg="#2c2c3a", fg="white", relief="flat",
          padx=12, pady=8, cursor="hand2").pack(side="left", padx=8)
tk.Button(row, text="Kendi gorsellerim", command=open_imgs, bg="#2c2c3a", fg="white", relief="flat",
          padx=12, pady=8, cursor="hand2").pack(side="left")

bar = ttk.Progressbar(root, mode="indeterminate")
bar.pack(fill="x", padx=14, pady=4)

log = scrolledtext.ScrolledText(root, bg="#0d0d13", fg="#d8d8e8", font=("Consolas", 9), relief="flat")
log.pack(fill="both", expand=True, padx=14, pady=(4, 14))

if not BOT.exists():
    messagebox.showerror("Dosya yok", "shorts_bot.py bu dosyayla ayni klasorde olmali.")

root.mainloop()
