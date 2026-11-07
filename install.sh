#!/bin/sh
set -eu

REPOSITORY="https://github.com/ard-tube/qdex"
VERSION="v1.0.0"
DEFAULT_INSTALL_DIR="$HOME/.local/share/qdex"
DEFAULT_BIN_DIR="$HOME/.local/bin"

printf 'Qdex installer\n'
printf 'Install Qdex files in [%s]: ' "$DEFAULT_INSTALL_DIR"
IFS= read -r install_dir || install_dir=""
install_dir=${install_dir:-$DEFAULT_INSTALL_DIR}

case "$install_dir" in
    "~") install_dir=$HOME ;;
    "~/"*) install_dir=$HOME/${install_dir#~/} ;;
esac

case "$install_dir" in
    /*) ;;
    *) install_dir=$PWD/$install_dir ;;
esac

archive=$(mktemp "${TMPDIR:-/tmp}/qdex.XXXXXX")
trap 'rm -f "$archive"' EXIT HUP INT TERM
url="$REPOSITORY/releases/download/$VERSION/qdex-$VERSION.tar.gz"
printf 'Downloading Qdex %s...\n' "$VERSION"
curl --fail --location --silent --show-error "$url" --output "$archive"
mkdir -p "$install_dir"
tar -xzf "$archive" -C "$install_dir" --strip-components=1

mkdir -p "$DEFAULT_BIN_DIR"
ln -sfn "$install_dir/qdex" "$DEFAULT_BIN_DIR/qdex"

add_path_line() {
    profile=$1
    line='export PATH="$HOME/.local/bin:$PATH"'
    touch "$profile"
    if ! grep -Fqx "$line" "$profile"; then
        printf '\n# Qdex command-line launcher\n%s\n' "$line" >> "$profile"
    fi
}

case "${SHELL##*/}" in
    zsh) add_path_line "$HOME/.zprofile" ;;
    bash) add_path_line "$HOME/.bash_profile" ;;
    fish)
        mkdir -p "$HOME/.config/fish"
        line='fish_add_path "$HOME/.local/bin"'
        touch "$HOME/.config/fish/config.fish"
        if ! grep -Fqx "$line" "$HOME/.config/fish/config.fish"; then
            printf '\n# Qdex command-line launcher\n%s\n' "$line" >> "$HOME/.config/fish/config.fish"
        fi
        ;;
    *)
        printf 'Added %s to PATH in your shell profile manually if needed.\n' "$DEFAULT_BIN_DIR"
        ;;
esac

printf '\nInstalled Qdex files at %s\n' "$install_dir"
printf 'Open a new terminal window and run: qdex\n'
