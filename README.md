# Qdex

Qdex is a keyboard-first terminal launcher and file browser for macOS, with a
neon command-center interface inspired by full-screen cyberpunk terminals. It
uses Python's standard library only: no account, paid license, App Store, or
extra Python packages are required.

## Install

Install with Homebrew:

```sh
brew install ard-tube/qdex/qdex
```

Or download and run the setup installer:

```sh
curl -fsSL https://ard-tube.github.io/qdex/install.sh | sh
```

The installer asks where to save Qdex, adds its launcher to `~/.local/bin`,
and updates the profile for zsh, bash, or fish. Open a new terminal window and
run `qdex`.

## Run

From this folder, run:

```sh
./qdex
```

For the full three-panel dashboard, maximize the Terminal window or use
full-screen mode and give it room (about 110 columns by 28 rows or larger). At
smaller sizes Qdex automatically switches to its compact layout.

For the dark macOS Terminal look, open **Terminal > Settings > Profiles**,
select the built-in **Pro** profile, and click **Default**. Qdex uses the
terminal's own background and draws its neon cyan, magenta, and green interface
on top.

Qdex requires macOS and Python 3.10 or newer. The first launch asks what name
to display and which folder to open by default. These preferences are saved in
`~/.config/qdex/config.json`. You can also run `python3 qdex.py` from source.

## Keys

| Key | Action |
| --- | --- |
| Type | Search the current folder or installed apps as you type |
| ↑ / ↓ or `j` / `k` | Move the selection |
| Enter | Open a folder, file, or app |
| Tab | Switch between file browsing and installed apps |
| Backspace | Edit search; with an empty search, go to the parent folder |
| Esc | Clear the search |
| F5 | Copy the selected file or folder to a destination folder |
| F6 | Move the selected file or folder to a destination folder |
| Page Up / Page Down | Move by a page |
| F10 | Quit |

Copy and move prompt for a destination folder. Existing destination items are
never overwritten. Hidden files are omitted by default; type a dot to search
for them. Qdex opens selected files and apps using macOS's `open` command.

Qdex is free to use and does not require Apple Developer Program membership or
App Store distribution. The Homebrew tap and website are published with this project; see the links on
the website for source and install instructions.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
