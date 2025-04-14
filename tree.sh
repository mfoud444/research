#!/bin/bash

# Directory to generate the tree for (default is the current directory)
directory="${1:-.}"

# Output file (default is output.txt)
output_file="${2:-output.txt}"

# Exclude directories
excluded_dirs="node_modules|trash|build|dist"

# Run the tree command and save output to file, excluding the specified folders
tree --prune -I "$excluded_dirs" "$directory" > "$output_file"

echo "Directory tree saved to $output_file, excluding specified folders."
