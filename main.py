"""Entry point for LogsFinder. This is the file PyInstaller builds.

Run during development with the REAL interpreter (the `python3` on PATH is a
Microsoft Store stub):

    C:\\Python314\\python.exe main.py
"""

import tkinter as tk
import traceback
from tkinter import messagebox

from logfinder.app import LogsFinderApp


def main():
    root = tk.Tk()
    try:
        LogsFinderApp(root)
    except Exception:
        # Construction failed before the UI was up — show it instead of dying silently.
        messagebox.showerror("LogsFinder — startup error", traceback.format_exc())
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
