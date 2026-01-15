# Plan: Convert update.sh to Fish and Expand Update Coverage

## Overview
Convert the bash update script to fish shell and expand it to cover all system package managers and tools (excluding uv-managed items per user request).

## File to Modify
- `/home/brian/.local/bin/update.sh` → rename to `update.fish`

## Detected Package Managers & Tools to Update

| Tool | Update Command | Clean Command |
|------|---------------|---------------|
| **apt** | `sudo apt update && sudo apt upgrade -y` | `sudo apt autoremove -y && sudo apt autoclean` |
| **snap** | `sudo snap refresh` | `snap list --all \| awk '/disabled/{print $1, $3}' \| xargs -rn2 sudo snap remove` (remove old revisions) |
| **flatpak** | `sudo flatpak update -y` | `sudo flatpak uninstall --unused -y` |
| **rustup** | `rustup update` | (none needed) |
| **volta** | `volta install node@latest` | (none needed) |
| **rbenv** | `cd ~/.rbenv && git pull` | (none needed) |
| **fisher** | `fisher update` | (none needed) |
| **pipx** | `pipx upgrade-all` | (none needed) |
| **ghostty** | Keep existing curl install script | (none needed) |
| **VS Code** | `code --update-extensions` | (none needed) |

## Pre-requisite: Install Fisher
Fisher is not currently installed. We'll install it first:
```fish
curl -sL https://raw.githubusercontent.com/jorgebucaran/fisher/main/functions/fisher.fish | source && fisher install jorgebucaran/fisher
```

## Excluded (per user request)
- `uv self update` - uv-controlled
- Zed - self-updates
- Cargo crates - only jless installed, not worth adding cargo-update dependency

## Proposed Script Structure

```fish
#!/usr/bin/env fish

# System packages
echo "=== Updating apt packages ==="
sudo apt update && sudo apt upgrade -y

echo "=== Updating snap packages ==="
sudo snap refresh

echo "=== Updating flatpak packages ==="
sudo flatpak update -y

# Development tools
echo "=== Updating Rust toolchain ==="
rustup update

echo "=== Updating Ruby (rbenv) ==="
if test -d ~/.rbenv
    git -C ~/.rbenv pull --quiet
end

echo "=== Updating Volta/Node ==="
volta install node@latest

echo "=== Updating pipx packages ==="
pipx upgrade-all

# Fish plugins (if fisher installed)
if type -q fisher
    echo "=== Updating fish plugins ==="
    fisher update
end

# IDE/Editor extensions
echo "=== Updating VS Code extensions ==="
code --update-extensions

# Applications
echo "=== Updating Ghostty ==="
curl -fsSL https://raw.githubusercontent.com/mkasberg/ghostty-ubuntu/HEAD/install.sh | bash

# Cleanup
echo "=== Cleaning up ==="
sudo apt autoremove -y
sudo apt autoclean
sudo flatpak uninstall --unused -y

# Clean old snap revisions
set old_snaps (snap list --all | awk '/disabled/{print $1, $3}')
if test -n "$old_snaps"
    echo $old_snaps | xargs -n2 sudo snap remove
end

echo "=== Update complete ==="
```

## Implementation Steps
1. Install fisher (one-time prerequisite)
2. Create `/home/brian/.local/bin/update.fish` with the script above
3. Remove or rename old `/home/brian/.local/bin/update.sh`
4. Make `update.fish` executable
