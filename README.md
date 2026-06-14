# LogsFinder

Search every line of **all** your Lunar Client session logs at once. Type a word or
phrase, and LogsFinder scans every `.log.gz` in your Lunar logs folder, shows a total
match count, and displays each hit with ~10 lines of context before and after, with
in-game `§` colors rendered, a "who said it" breakdown, and scope/date filters.

Built for Hypixel chat history, but works on any Lunar Client 1.8 logs.

---

## Download

1. Go to the **[Releases page](../../releases)** and download **`LogsFinder.exe`**
   (or the `LogsFinder-vX.Y.Z.zip`, which also includes this README).
2. Put it anywhere you like: Desktop, Downloads, a folder, it doesn't matter. It's a
   single self-contained program; there is **nothing to install**.
3. Double-click it. The **first** time, Windows shows a blue box:
   > "Windows protected your PC"

   This appears for any app that isn't signed by a big company, it is **not** a virus
   warning about this program. Click **More info → Run anyway**.
4. The window opens, loads your logs (a few seconds), and you can search.

> **Your logs never leave your PC.** LogsFinder reads your local log files and shows them
> to you. Nothing is uploaded anywhere, and your chat logs are never part of this project.

It reads your logs straight from:

```
C:\Users\<you>\.lunarclient\profiles\1.8\logs
```

You never have to unzip, copy, or import anything. After you play more sessions, click
**Refresh** to pick up the new logs.

---

## Using it

- **Search box**: type any text, then press Enter or click Find.
- **Show: All lines / Chat only / My messages**: "My messages" finds only what *you*
  typed. Your name is detected per session from each log, so it keeps working after you
  rename in-game.
- **Context lines**: how many lines to show around each match (default 10).
- **Ignore case**: on by default (so `GG` finds `gg`).
- **Regex**: advanced: treat the search as a regular expression.
- **Colors**: render Minecraft `§` color codes like in-game. Turn off
  for plain text.
- **Dates: From / To** (`YYYY-MM-DD`, blank = open) plus quick buttons **All / Last 7d /
  Last 30d** to narrow results to a date range.
- **Refresh**: re-scan the folder after you've played more.
- **Browse folder…**: point it at a different logs folder (another profile, or wherever
  your logs live). Pick the folder that directly contains the `.log.gz` files. Your choice
  is remembered, so the app reopens there next time.

The matched line is highlighted with an amber band.

### "Who said it" panel (right side)

Shows which players said your search word and how many times, most first. Lines that
aren't a player's chat message (game/system announcements) are grouped as **system**.
Your own names are marked **(you)**. Click a name to show only that person's matches;
click **All** to go back.

> Tip: search matches the visible text, so don't include `§` color codes in your search —
> search the words as they appear on screen.

---

## License

[MIT](LICENSE) © 2026 Arda-exe
