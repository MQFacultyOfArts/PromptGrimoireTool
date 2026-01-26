#!/bin/bash
# Save clipboard HTML to output/ for CSS analysis
# Usage: ./scripts/save_chat.sh <source_name>
# Example: ./scripts/save_chat.sh openai

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <source_name>"
    echo "Example: $0 openai"
    exit 1
fi

OUTPUT_DIR="$(dirname "$0")/../output"
mkdir -p "$OUTPUT_DIR"

OUTPUT_FILE="$OUTPUT_DIR/chat_$1.html"

xclip -selection clipboard -t text/html -o > "$OUTPUT_FILE"

BYTES=$(wc -c < "$OUTPUT_FILE")
echo "Saved $BYTES bytes to $OUTPUT_FILE"
