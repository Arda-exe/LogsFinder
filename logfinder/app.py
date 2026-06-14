"""Tkinter UI for LogsFinder.

All widget access happens on the main thread. Loading and searching run on a
background thread that communicates back through a queue.Queue, which the main
thread drains with root.after(). The worker never touches a widget.

The results pane is a dark, Minecraft-style view that renders § color codes.
A side panel breaks down who said the searched word; clicking a name filters
the view to that person. Scope (all/chat/mine) and a date range narrow results.
"""

import datetime
import queue
import re
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cache import LogCache
from .logs import find_log_files
from .parse import sanitize, segment_colors, split_prefix
from .search import search
from .settings import load_settings, save_settings

DEFAULT_LOGS = Path.home() / ".lunarclient" / "profiles" / "1.8" / "logs"
MONO = ("Consolas", 10)
MONO_BOLD = ("Consolas", 10, "bold")

# Minecraft color palette (§0 black remapped lighter so it shows on the dark pane).
MC_COLORS = {
    "0": "#4d4d4d", "1": "#3b3bff", "2": "#00AA00", "3": "#00AAAA",
    "4": "#cc3333", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
    "8": "#777777", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF",
}
BG = "#1e1e1e"
FG = "#dddddd"


def _resource_path(name):
    """Locate a bundled resource, both from source and inside the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)  # set when running as a frozen exe
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return Path(base) / name


class LogsFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LogsFinder")
        try:
            self.root.iconbitmap(str(_resource_path("app.ico")))
        except tk.TclError:
            pass  # icon file missing (e.g. running from source without app.ico)
        self.root.geometry("1180x680")
        self.root.minsize(820, 460)
        self.root.report_callback_exception = self._report_callback_exception

        self.cache = LogCache()
        self.settings = load_settings()
        saved = self.settings.get("folder")
        self.folder = Path(saved) if saved and Path(saved).is_dir() else DEFAULT_LOGS
        self.files = []
        self.loaded = False
        self.busy = False
        self.q = queue.Queue()

        self._last_result = None
        self._speaker_filter = None  # None = show all; else a speaker name
        self._bd_items = {}          # Treeview item id -> speaker name (None for "All")

        self._build_widgets()
        self.root.after(50, self._poll_queue)
        self._start_load()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # Row 0 — search box + Find
        top = ttk.Frame(root, padding=(8, 8, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Search:").grid(row=0, column=0, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.entry = ttk.Entry(top, textvariable=self.search_var)
        self.entry.grid(row=0, column=1, sticky="ew")
        self.entry.bind("<Return>", lambda e: self._on_find())
        self.entry.focus_set()
        self.find_btn = ttk.Button(top, text="Find", command=self._on_find)
        self.find_btn.grid(row=0, column=2, padx=(6, 0))

        # Row 1 — options (two sub-rows inside one frame)
        opts = ttk.Frame(root, padding=(8, 0, 8, 6))
        opts.grid(row=1, column=0, sticky="ew")

        # sub-row a: scope + match options + colors + refresh/browse
        ttk.Label(opts, text="Show:").grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.scope_var = tk.StringVar(value="all")
        self.scope_all = ttk.Radiobutton(opts, text="All lines", value="all", variable=self.scope_var)
        self.scope_chat = ttk.Radiobutton(opts, text="Chat only", value="chat", variable=self.scope_var)
        self.scope_mine = ttk.Radiobutton(opts, text="My messages", value="mine", variable=self.scope_var)
        self.scope_all.grid(row=0, column=1, sticky="w")
        self.scope_chat.grid(row=0, column=2, sticky="w")
        self.scope_mine.grid(row=0, column=3, sticky="w", padx=(0, 12))

        ttk.Label(opts, text="Context:").grid(row=0, column=4, padx=(0, 4))
        self.context_var = tk.StringVar(value="10")
        self.context_spin = ttk.Spinbox(opts, from_=0, to=100, width=4, textvariable=self.context_var)
        self.context_spin.grid(row=0, column=5, padx=(0, 12))

        self.case_var = tk.BooleanVar(value=True)
        self.case_chk = ttk.Checkbutton(opts, text="Ignore case", variable=self.case_var)
        self.case_chk.grid(row=0, column=6, padx=(0, 8))
        self.regex_var = tk.BooleanVar(value=False)
        self.regex_chk = ttk.Checkbutton(opts, text="Regex", variable=self.regex_var)
        self.regex_chk.grid(row=0, column=7, padx=(0, 8))
        self.colors_var = tk.BooleanVar(value=True)
        self.colors_chk = ttk.Checkbutton(opts, text="Colors", variable=self.colors_var,
                                           command=self._render_results)
        self.colors_chk.grid(row=0, column=8, padx=(0, 12))

        self.refresh_btn = ttk.Button(opts, text="Refresh", command=self._on_refresh)
        self.refresh_btn.grid(row=0, column=9, padx=(0, 6))
        self.browse_btn = ttk.Button(opts, text="Browse folder…", command=self._on_browse)
        self.browse_btn.grid(row=0, column=10)

        # sub-row b: date range + presets
        dates = ttk.Frame(opts)
        dates.grid(row=1, column=0, columnspan=11, sticky="w", pady=(6, 0))
        ttk.Label(dates, text="Dates:  From").grid(row=0, column=0, padx=(0, 4))
        self.date_from_var = tk.StringVar()
        self.date_from = ttk.Entry(dates, width=12, textvariable=self.date_from_var)
        self.date_from.grid(row=0, column=1, padx=(0, 8))
        ttk.Label(dates, text="To").grid(row=0, column=2, padx=(0, 4))
        self.date_to_var = tk.StringVar()
        self.date_to = ttk.Entry(dates, width=12, textvariable=self.date_to_var)
        self.date_to.grid(row=0, column=3, padx=(0, 4))
        ttk.Label(dates, text="(YYYY-MM-DD, blank = open)").grid(row=0, column=4, padx=(0, 12))
        self.preset_all = ttk.Button(dates, text="All", width=5, command=lambda: self._preset(None))
        self.preset_7 = ttk.Button(dates, text="Last 7d", width=8, command=lambda: self._preset(7))
        self.preset_30 = ttk.Button(dates, text="Last 30d", width=9, command=lambda: self._preset(30))
        self.preset_all.grid(row=0, column=5, padx=(0, 4))
        self.preset_7.grid(row=0, column=6, padx=(0, 4))
        self.preset_30.grid(row=0, column=7)

        # Row 2 — body: results (left) + speaker breakdown (right)
        body = ttk.Panedwindow(root, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(body)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.results = tk.Text(left, wrap="none", font=MONO, state="disabled",
                               background=BG, foreground=FG, insertbackground=FG,
                               padx=6, pady=6, cursor="arrow", borderwidth=0)
        self.results.grid(row=0, column=0, sticky="nsew")
        vbar = ttk.Scrollbar(left, orient="vertical", command=self.results.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        hbar = ttk.Scrollbar(left, orient="horizontal", command=self.results.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        self.results.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        body.add(left, weight=4)

        right = ttk.Frame(body)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="Who said it  (click to filter)").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 2))
        self.breakdown = ttk.Treeview(right, columns=("name", "count"), show="headings",
                                      selectmode="browse")
        self.breakdown.heading("name", text="User")
        self.breakdown.heading("count", text="#")
        self.breakdown.column("name", width=150, anchor="w")
        self.breakdown.column("count", width=46, anchor="e", stretch=False)
        self.breakdown.grid(row=1, column=0, sticky="nsew")
        bdbar = ttk.Scrollbar(right, orient="vertical", command=self.breakdown.yview)
        bdbar.grid(row=1, column=1, sticky="ns")
        self.breakdown.configure(yscrollcommand=bdbar.set)
        self.breakdown.bind("<<TreeviewSelect>>", self._on_breakdown_select)
        body.add(right, weight=1)

        # results tags
        t = self.results
        for key, hexv in MC_COLORS.items():
            t.tag_configure(f"mc_{key}", foreground=hexv)
        t.tag_configure("prefix", foreground="#7a7a7a")
        t.tag_configure("header", font=MONO_BOLD, foreground="#6fb3ff", spacing1=8, spacing3=2)
        t.tag_configure("match_band", background="#4a3f1e")
        t.tag_configure("arrow", foreground="#ffcf5a")
        t.tag_configure("sep", foreground="#555555")
        t.tag_configure("info", foreground="#888888")

        # Row 3 — status / headline
        self.status_var = tk.StringVar(value="Starting…")
        ttk.Label(root, textvariable=self.status_var, padding=(10, 3), anchor="w").grid(
            row=3, column=0, sticky="ew")

    def _controls(self):
        return (
            self.find_btn, self.refresh_btn, self.browse_btn, self.entry,
            self.context_spin, self.case_chk, self.regex_chk,
            self.scope_all, self.scope_chat, self.scope_mine,
            self.date_from, self.date_to, self.preset_all, self.preset_7, self.preset_30,
        )

    def _set_controls_enabled(self, enabled):
        flag = "!disabled" if enabled else "disabled"
        for w in self._controls():
            try:
                w.state([flag])
            except tk.TclError:
                pass

    # -------------------------------------------------------------- actions
    def _parse_date(self, s):
        """Return (date|None, ok). Empty string is valid (unbounded)."""
        s = s.strip()
        if not s:
            return None, True
        try:
            return datetime.datetime.strptime(s, "%Y-%m-%d").date(), True
        except ValueError:
            return None, False

    def _preset(self, days):
        if days is None:
            self.date_from_var.set("")
            self.date_to_var.set("")
        else:
            today = datetime.date.today()
            self.date_from_var.set((today - datetime.timedelta(days=days - 1)).isoformat())
            self.date_to_var.set("")
        if self.loaded and not self.busy and self.search_var.get().strip():
            self._on_find()

    def _on_find(self):
        if self.busy or not self.loaded:
            return
        query = self.search_var.get()
        if not query.strip():
            self.status_var.set("Type a word or phrase to search for.")
            return
        df, ok1 = self._parse_date(self.date_from_var.get())
        dt_, ok2 = self._parse_date(self.date_to_var.get())
        if not (ok1 and ok2):
            self.status_var.set("Dates must be YYYY-MM-DD (or left blank).")
            return
        if df is not None and dt_ is not None and df > dt_:
            self.status_var.set("The 'From' date is after the 'To' date.")
            return
        try:
            context = int(self.context_var.get())
        except (ValueError, tk.TclError):
            context = 10
        context = max(0, min(context, 1000))

        self.busy = True
        self._set_controls_enabled(False)
        self.status_var.set("Searching…")
        threading.Thread(
            target=self._search_worker,
            args=(query, self.regex_var.get(), self.case_var.get(), context,
                  self.scope_var.get(), df, dt_),
            daemon=True,
        ).start()

    def _on_refresh(self):
        if self.busy:
            return
        self.cache.clear()
        self._start_load()

    def _on_browse(self):
        if self.busy:
            return
        initial = str(self.folder) if Path(self.folder).is_dir() else str(Path.home())
        chosen = filedialog.askdirectory(title="Select your Lunar Client logs folder",
                                         initialdir=initial)
        if chosen:
            self.folder = Path(chosen)
            self.settings["folder"] = str(self.folder)
            save_settings(self.settings)
            self.cache.clear()
            self._start_load()

    # --------------------------------------------------------------- workers
    def _start_load(self):
        self.busy = True
        self.loaded = False
        self._set_controls_enabled(False)
        self.status_var.set("Loading logs…")
        threading.Thread(target=self._load_worker, args=(self.folder,), daemon=True).start()

    def _load_worker(self, folder):
        try:
            files = find_log_files(folder)
            total = len(files)
            for i, path in enumerate(files, 1):
                self.cache.get_file(path)  # warm the cache
                if i % 4 == 0 or i == total:
                    self.q.put(("progress", i, total))
            self.q.put(("loaded", files))
        except Exception as exc:  # pragma: no cover - defensive
            self.q.put(("error", f"Failed to load logs: {exc}"))

    def _search_worker(self, query, regex, ignore_case, context, scope, date_from, date_to):
        try:
            result = search(self.cache, self.files, query, regex=regex, ignore_case=ignore_case,
                            context=context, scope=scope, date_from=date_from, date_to=date_to)
            self.q.put(("result", result))
        except re.error as exc:
            self.q.put(("error", f"Invalid regex pattern: {exc}"))
        except Exception as exc:  # pragma: no cover - defensive
            self.q.put(("error", f"Search failed: {exc}"))

    # ------------------------------------------------------------ main thread
    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, i, total = msg
                    self.status_var.set(f"Loading logs… {i}/{total} files")
                elif kind == "loaded":
                    _, files = msg
                    self.files = files
                    self.loaded = True
                    self.busy = False
                    self._set_controls_enabled(True)
                    if not files:
                        self.status_var.set(
                            f"No log files found in: {self.folder}   —   "
                            "click “Browse folder…” to pick your Lunar logs folder.")
                    else:
                        self.status_var.set(
                            f"Ready — {len(files)} log files loaded. "
                            "Type a word or phrase and click Find.")
                elif kind == "result":
                    _, result = msg
                    self.busy = False
                    self._set_controls_enabled(True)
                    self._render(result)
                elif kind == "error":
                    _, message = msg
                    self.busy = False
                    self._set_controls_enabled(True)
                    self.status_var.set(message)
                    messagebox.showerror("LogsFinder", message)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    # ----------------------------------------------------------- rendering
    def _render(self, result):
        self._last_result = result
        self._speaker_filter = None

        parts = [f"Total matches: {result.total_count:,} across {result.files_searched} files"]
        if result.truncated:
            parts.append(f"showing first {len(result.blocks):,} passages — narrow your search")
        if result.skipped:
            parts.append(f"skipped: {', '.join(result.skipped)}")
        if self.scope_var.get() == "mine" and not result.self_names:
            parts.append("(no 'Setting user' name found — can't identify your messages)")
        self.status_var.set("    ·    ".join(parts))

        self._populate_breakdown(result)
        self._render_results()

    def _populate_breakdown(self, result):
        tv = self.breakdown
        tv.delete(*tv.get_children())
        self._bd_items = {}
        all_id = tv.insert("", "end", values=("All", f"{result.total_count:,}"))
        self._bd_items[all_id] = None
        for name, cnt in sorted(result.speakers.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            label = name
            if name != "system" and name in result.self_names:
                label = f"{name} (you)"
            iid = tv.insert("", "end", values=(label, f"{cnt:,}"))
            self._bd_items[iid] = name

    def _on_breakdown_select(self, event=None):
        sel = self.breakdown.selection()
        if not sel:
            return
        name = self._bd_items.get(sel[0])
        if name != self._speaker_filter:
            self._speaker_filter = name
            self._render_results()

    def _render_results(self):
        result = self._last_result
        t = self.results
        t.configure(state="normal")
        t.delete("1.0", "end")

        if result is None or result.total_count == 0:
            msg = "No matches." if result is None else f"No matches for “{result.query}”."
            t.insert("end", f"\n   {msg}\n", "info")
            t.configure(state="disabled")
            return

        show_colors = self.colors_var.get()
        spk = self._speaker_filter
        last_file = None
        for block in result.blocks:
            if spk is not None and not any(
                    lv.is_match and lv.speaker == spk for lv in block.lines):
                continue
            if block.file != last_file:
                t.insert("end", f"═══  {block.file}  ═══════\n", "header")
                last_file = block.file
            else:
                t.insert("end", "          ·  ·  ·\n", "sep")
            for lv in block.lines:
                self._insert_line(lv, show_colors, spk)

        t.configure(state="disabled")
        t.yview_moveto(0.0)

    def _insert_line(self, lv, show_colors, spk):
        t = self.results
        is_match = lv.is_match and (spk is None or lv.speaker == spk)
        start = t.index("end-1c")
        t.insert("end", "  ▶ " if is_match else "    ", ("arrow",) if is_match else ())

        # Full control-char sanitation happens here (render time), not at load —
        # only the handful of displayed lines pay for it.
        src = sanitize(lv.raw if show_colors else lv.stripped)
        prefix, payload = split_prefix(src)
        if prefix:
            t.insert("end", prefix, ("prefix",))
        if show_colors:
            for text, key in segment_colors(payload):
                if text:
                    t.insert("end", text, (f"mc_{key}",) if key else ())
        elif payload:
            t.insert("end", payload)

        end = t.index("end-1c")
        t.insert("end", "\n")
        if is_match:
            t.tag_add("match_band", start, end)

    def _report_callback_exception(self, exc, val, tb):
        messagebox.showerror(
            "LogsFinder — unexpected error",
            "".join(traceback.format_exception(exc, val, tb)),
        )
