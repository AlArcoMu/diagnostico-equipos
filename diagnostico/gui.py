import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import analysis
from .app import default_folder, run

INK = "#13253a"
ACCENT = "#e2541c"
ACCENT_HOVER = "#c94612"
BG = "#eef1f5"
MUTED = "#5c6b7a"
FONT = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class App(tk.Tk):
    def __init__(self, demo=False, days=7, folder=None):
        super().__init__()
        self.demo = demo
        self.folder = tk.StringVar(value=str(folder or default_folder()))
        self.days = tk.IntVar(value=days)
        self.ticket = tk.StringVar()
        self.status = tk.StringVar(value="Rellena los datos del ticket si los tienes y pulsa Ejecutar diagnóstico.")
        self.events = queue.Queue()
        self.result = None

        self.title("Diagnóstico de equipos")
        self.configure(bg=BG)
        self.minsize(540, 620)
        self._icon()
        self._styles()
        self._build()

    def _icon(self):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        ico = base / "assets" / "icon.ico"
        if sys.platform == "win32" and ico.exists():
            self.iconbitmap(default=str(ico))

    def _styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground=INK, font=(FONT, 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        style.configure("Field.TLabel", background="#ffffff", foreground=INK, font=(FONT, 10, "bold"))
        style.configure("TEntry", padding=6, fieldbackground="#ffffff")
        style.configure("TSpinbox", padding=4, arrowsize=12)
        style.configure("Ghost.TButton", font=(FONT, 10), padding=(10, 5), background="#ffffff", foreground=INK, bordercolor="#c9d2dc")
        style.map("Ghost.TButton", background=[("active", "#f2f4f7")])
        style.configure("Bar.Horizontal.TProgressbar", troughcolor="#dde3ea", background=ACCENT, bordercolor="#dde3ea", lightcolor=ACCENT, darkcolor=ACCENT)

    def _build(self):
        header = tk.Frame(self, bg=INK, padx=24, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="Diagnóstico de equipos", bg=INK, fg="#ffffff", font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(header, text="Genera un informe del equipo para adjuntarlo al ticket", bg=INK, fg="#c9d2dc", font=(FONT, 10)).pack(anchor="w")

        body = ttk.Frame(self, padding=(20, 18, 20, 8))
        body.pack(fill="both", expand=True)
        card = ttk.Frame(body, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Nº de ticket (opcional)", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(card, textvariable=self.ticket).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(card, text="¿Qué problema indica el usuario?", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        self.problem = tk.Text(card, height=4, wrap="word", font=(FONT, 10), relief="solid", bd=1, highlightthickness=0, padx=6, pady=4)
        self.problem.grid(row=3, column=0, sticky="ew", pady=(4, 12))

        days_row = ttk.Frame(card, style="Card.TFrame")
        days_row.grid(row=4, column=0, sticky="w", pady=(0, 12))
        ttk.Label(days_row, text="Revisar el visor de eventos de los últimos").pack(side="left")
        ttk.Spinbox(days_row, from_=1, to=30, width=4, textvariable=self.days).pack(side="left", padx=6)
        ttk.Label(days_row, text="días").pack(side="left")

        ttk.Label(card, text="Guardar el informe en", style="Field.TLabel").grid(row=5, column=0, sticky="w")
        folder_row = ttk.Frame(card, style="Card.TFrame")
        folder_row.grid(row=6, column=0, sticky="ew", pady=(4, 16))
        folder_row.columnconfigure(0, weight=1)
        ttk.Entry(folder_row, textvariable=self.folder).grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_row, text="Cambiar…", style="Ghost.TButton", command=self._pick_folder).grid(row=0, column=1, padx=(8, 0))

        self.run_btn = tk.Button(card, text="Ejecutar diagnóstico", command=self._start, bg=ACCENT, fg="#ffffff",
                                 activebackground=ACCENT_HOVER, activeforeground="#ffffff", relief="flat",
                                 font=(FONT, 12, "bold"), padx=16, pady=10, cursor="hand2", bd=0)
        self.run_btn.grid(row=7, column=0, sticky="ew")

        self.progress = ttk.Progressbar(card, mode="indeterminate", style="Bar.Horizontal.TProgressbar")
        self.progress.grid(row=8, column=0, sticky="ew", pady=(14, 6))
        self.progress.grid_remove()

        self.status_lbl = ttk.Label(card, textvariable=self.status, foreground=MUTED, wraplength=440, justify="left")
        self.status_lbl.grid(row=9, column=0, sticky="w", pady=(8, 0))

        self.done_row = ttk.Frame(card, style="Card.TFrame")
        self.done_row.grid(row=10, column=0, sticky="w", pady=(12, 0))
        for text, cmd in (("Abrir informe", self._open_report), ("Abrir carpeta", self._open_folder), ("Copiar resumen", self._copy)):
            ttk.Button(self.done_row, text=text, style="Ghost.TButton", command=cmd).pack(side="left", padx=(0, 8))
        self.done_row.grid_remove()

        footer = "Modo demostración: se usan datos de ejemplo." if self.demo else "Solo lee información del equipo; no cambia nada."
        ttk.Label(self, text=footer, style="Muted.TLabel").pack(pady=(0, 12))

    def _pick_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder.get(), title="Carpeta para los informes")
        if chosen:
            self.folder.set(chosen)

    def _start(self):
        self.run_btn.configure(state="disabled", text="Diagnosticando…", bg="#9aa6b2")
        self.done_row.grid_remove()
        self.progress.grid()
        self.progress.start(12)
        args = dict(days=max(1, min(30, int(self.days.get() or 7))), ticket=self.ticket.get().strip(),
                    problem=self.problem.get("1.0", "end").strip(), folder=self.folder.get().strip() or None, demo=self.demo)
        threading.Thread(target=self._work, kwargs=args, daemon=True).start()
        self.after(100, self._poll)

    def _work(self, **kwargs):
        try:
            result = run(progress=lambda m: self.events.put(("status", m)), **kwargs)
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", exc))

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status.set(payload)
                elif kind == "done":
                    return self._finish(payload)
                else:
                    return self._fail(payload)
        except queue.Empty:
            self.after(100, self._poll)

    def _reset(self):
        self.progress.stop()
        self.progress.grid_remove()
        self.run_btn.configure(state="normal", text="Ejecutar diagnóstico", bg=ACCENT)

    def _finish(self, result):
        self._reset()
        self.result = result
        html, findings, _ = result
        crit = sum(f["level"] == analysis.CRITICAL for f in findings)
        warn = len(findings) - crit
        if not findings:
            msg = "Listo. No se han encontrado problemas."
        else:
            parts = [analysis.plural(crit, "crítico", "críticos")] if crit else []
            parts += [analysis.plural(warn, "aviso", "avisos")] if warn else []
            msg = f"Listo. {' y '.join(parts).capitalize()}."
        self.status.set(f"{msg}\nInforme guardado: {html.name}")
        self.done_row.grid()
        self._open_report()

    def _fail(self, exc):
        self._reset()
        self.status.set("No se ha podido completar el diagnóstico.")
        messagebox.showerror("Diagnóstico de equipos", f"No se ha podido completar el diagnóstico.\n\n{exc}")

    def _open_report(self):
        if self.result:
            webbrowser.open(self.result[0].resolve().as_uri())

    def _open_folder(self):
        if self.result:
            open_path(self.result[0].parent)

    def _copy(self):
        if self.result:
            self.clipboard_clear()
            self.clipboard_append(self.result[2])
            self.status.set("Resumen copiado. Pégalo en el ticket.")
