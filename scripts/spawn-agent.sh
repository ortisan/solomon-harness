#!/usr/bin/env bash

set -euo pipefail

agents_dir=".agents/agents"

# Display usage instructions
show_help() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  list                  Lists all available subagents."
    echo "  show <agent_name>     Displays the prompt profile of the specified subagent."
    echo "  help, -h, --help      Displays this usage message."
}

if [ "$#" -lt 1 ]; then
    show_help >&2
    exit 1
fi

command="$1"

case "$command" in
    help|-h|--help)
        show_help
        exit 0
        ;;
    list)
        if [ ! -d "$agents_dir" ]; then
            echo "Error: Subagents directory '$agents_dir' not found." >&2
            exit 1
        fi
        
        echo "Available subagents:"
        
        shopt -s nullglob
        found=false
        for agent_file in "$agents_dir"/*.md; do
            found=true
            filename=$(basename "$agent_file")
            agent_name="${filename%.md}"
            
            # Extract first non-empty line that does not start with '#'
            description=$(awk '/^[^#]/ { if (NF > 0) { print; exit } }' "$agent_file")
            
            echo "  $agent_name - $description"
        done
        shopt -u nullglob
        
        if [ "$found" = false ]; then
            echo "No subagents found in '$agents_dir'."
        fi
        ;;
    show)
        if [ "$#" -lt 2 ]; then
            echo "Error: Subcommand 'show' requires an agent name." >&2
            exit 1
        fi
        
        agent_name="$2"
        agent_file="$agents_dir/${agent_name}.md"
        
        if [ ! -f "$agent_file" ]; then
            echo "Error: Subagent '$agent_name' does not exist." >&2
            exit 1
        fi
        
        cat "$agent_file"
        ;;
    *)
        echo "Error: Invalid command '$command'." >&2
        show_help >&2
        exit 1
        ;;
esac
