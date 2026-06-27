#!/usr/bin/env bash

# Scrum Master & Issue Management Script
# Conform strictly to the Solomon Agent Setup design contract.

set -euo pipefail

# Initialize global variables
REPO=""
DRY_RUN=false
IS_MOCK=false

# Help usage function
show_help() {
  cat <<EOF
Scrum Master & Issue Management Script

Usage:
  $0 [global options] <subcommand> [subcommand arguments]

Global Options:
  -R, --repo <owner/repo>   Specify GitHub repository (e.g. "owner/repo")
  --dry-run                 Simulate API calls without executing them
  -h, --help                Show this help message

Subcommands:
  milestone-create <title> <description> <due-date>
      Creates a GitHub milestone.
      <due-date> can be formatted as YYYY-MM-DD or ISO 8601.

  issue-create <title> <type: feature|bug|quant|future> [description]
      Creates a GitHub issue using the corresponding template:
        - feature: feature_conception.md
        - bug:     bug_report.md
        - quant:   quant_model_hypothesis.md
        - future:  future_ideas.md

  backlog-list
      Lists open issues in the repository.

  milestone-list
      Lists milestones in the repository.

Examples:
  $0 milestone-create "Sprint 1" "Initial Setup" "2026-07-15"
  $0 issue-create "Implement backtest pipeline" "quant" "Implement walk-forward analysis"
  $0 backlog-list
EOF
}

# Parse global options
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -R|--repo)
      if [[ -z "${2:-}" ]]; then
        echo "Error: --repo requires an argument." >&2
        exit 1
      fi
      REPO="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -*)
      echo "Error: Unknown option $1" >&2
      show_help >&2
      exit 1
      ;;
    *)
      # First argument that doesn't start with - is the subcommand
      break
      ;;
  esac
done

# Check if subcommand is provided
if [[ $# -eq 0 ]]; then
  echo "Error: Subcommand is required." >&2
  show_help >&2
  exit 1
fi

SUBCOMMAND="$1"
shift

# Resolve repository if not provided
if [[ -z "$REPO" ]]; then
  if git rev-parse --is-inside-work-tree &>/dev/null; then
    REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
    if [[ -n "$REMOTE_URL" ]]; then
      # Handle SSH and HTTPS formats
      if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
        REPO="${BASH_REMATCH[1]}"
      fi
    fi
  fi
fi

# Determine if we should mock (if no repo is found and not in dry-run mode)
if [[ -z "$REPO" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    REPO="mock/repo"
  else
    echo "Warning: No GitHub repository detected (no git remote origin found or --repo not set)." >&2
    echo "Running in mock/simulation mode." >&2
    IS_MOCK=true
    REPO="mock/repo"
  fi
fi

# Verify gh CLI is installed if not mocking
if [[ "$IS_MOCK" == "false" ]]; then
  if ! command -v gh &>/dev/null; then
    echo "Error: GitHub CLI (gh) is not installed. Please install it or run in mock mode." >&2
    exit 1
  fi
fi

# Helper to parse YAML frontmatter and body from templates
parse_template() {
  local template_file="$1"
  local in_frontmatter=false
  TEMPLATE_BODY=""
  TEMPLATE_LABELS=""
  
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "---" ]]; then
      if [[ "$in_frontmatter" == "false" && -z "$TEMPLATE_BODY" ]]; then
        in_frontmatter=true
        continue
      elif [[ "$in_frontmatter" == "true" ]]; then
        in_frontmatter=false
        continue
      fi
    fi
    
    if [[ "$in_frontmatter" == "true" ]]; then
      if [[ "$line" =~ ^labels:[[:space:]]*\[(.*)\] ]]; then
        # Strip quotes and spaces
        TEMPLATE_LABELS=$(echo "${BASH_REMATCH[1]}" | tr -d '"' | tr -d "'" | tr -d ' ')
      fi
    else
      TEMPLATE_BODY+="$line"$'\n'
    fi
  done < "$template_file"
}

# Execute subcommands
if [[ "$SUBCOMMAND" == "milestone-create" ]]; then
  if [[ $# -lt 3 ]]; then
    echo "Error: milestone-create requires <title>, <description>, and <due-date>." >&2
    exit 1
  fi
  TITLE="$1"
  DESCRIPTION="$2"
  DUE_DATE="$3"
  
  # Format due date to ISO 8601 if needed
  if [[ "$DUE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    DUE_ON="${DUE_DATE}T23:59:59Z"
  else
    DUE_ON="$DUE_DATE"
  fi

  if [[ "$DRY_RUN" == "true" || "$IS_MOCK" == "true" ]]; then
    echo "[DRY RUN / MOCK] Would create milestone in repo: $REPO"
    echo "  Title:       $TITLE"
    echo "  Description: $DESCRIPTION"
    echo "  Due Date:    $DUE_ON"
    exit 0
  fi

  echo "Creating milestone '$TITLE' on GitHub repository '$REPO'..."
  
  # Run and catch error output
  MILESTONE_NUMBER=$(gh api -X POST "repos/$REPO/milestones" \
    -f title="$TITLE" \
    -f description="$DESCRIPTION" \
    -f due_on="$DUE_ON" \
    --jq '.number' 2>err.log) || {
      echo "Error creating milestone:" >&2
      cat err.log >&2
      rm -f err.log
      exit 1
    }
  rm -f err.log

  echo "Milestone successfully created: #$MILESTONE_NUMBER"
  exit 0

elif [[ "$SUBCOMMAND" == "issue-create" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "Error: issue-create requires <title> and <type: feature|bug|quant|future>." >&2
    exit 1
  fi
  TITLE="$1"
  TYPE="$2"
  DESCRIPTION="${3:-}"

  # Validate type and assign template path
  TEMPLATE_PATH=""
  case "$TYPE" in
    feature)
      TEMPLATE_PATH=".github/ISSUE_TEMPLATE/feature_conception.md"
      ;;
    bug)
      TEMPLATE_PATH=".github/ISSUE_TEMPLATE/bug_report.md"
      ;;
    quant)
      TEMPLATE_PATH=".github/ISSUE_TEMPLATE/quant_model_hypothesis.md"
      ;;
    future)
      TEMPLATE_PATH=".github/ISSUE_TEMPLATE/future_ideas.md"
      ;;
    *)
      echo "Error: Invalid type '$TYPE'. Must be one of: feature, bug, quant, future." >&2
      exit 1
      ;;
  esac

  # Find git root or workspace root
  GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -z "$GIT_ROOT" ]]; then
    # Fallback to parent of script directory or current directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    GIT_ROOT="$(dirname "$SCRIPT_DIR")"
  fi

  FULL_TEMPLATE_PATH="$GIT_ROOT/$TEMPLATE_PATH"
  if [[ ! -f "$FULL_TEMPLATE_PATH" ]]; then
    echo "Error: Template file not found at $FULL_TEMPLATE_PATH" >&2
    exit 1
  fi

  # Parse template file
  parse_template "$FULL_TEMPLATE_PATH"

  # Inject description into template placeholders if provided
  if [[ -n "$DESCRIPTION" ]]; then
    if [[ "$TYPE" == "feature" ]]; then
      TEMPLATE_BODY="${TEMPLATE_BODY/<!-- Provide a clear and concise description of what the feature is. -->/$DESCRIPTION}"
    elif [[ "$TYPE" == "bug" ]]; then
      TEMPLATE_BODY="${TEMPLATE_BODY/<!-- A clear and concise description of what the bug is. -->/$DESCRIPTION}"
    elif [[ "$TYPE" == "quant" ]]; then
      TEMPLATE_BODY="${TEMPLATE_BODY/<!-- State the underlying economic or statistical rationale for this model. What market inefficiency or pattern is being exploited? -->/$DESCRIPTION}"
    elif [[ "$TYPE" == "future" ]]; then
      TEMPLATE_BODY="${TEMPLATE_BODY/<!-- Provide a clear and concise description of the idea. -->/$DESCRIPTION}"
    fi
  fi

  if [[ "$DRY_RUN" == "true" || "$IS_MOCK" == "true" ]]; then
    echo "[DRY RUN / MOCK] Would create issue in repo: $REPO"
    echo "  Title:       $TITLE"
    echo "  Type:        $TYPE"
    echo "  Labels:      $TEMPLATE_LABELS"
    echo "  Body Preview (first 5 lines):"
    echo "$TEMPLATE_BODY" | head -n 5
    exit 0
  fi

  # Write the processed body to a temporary file
  TMP_BODY_FILE=$(mktemp)
  echo "$TEMPLATE_BODY" > "$TMP_BODY_FILE"

  echo "Creating issue '$TITLE' on GitHub repository '$REPO'..."
  
  # Build gh issue create command array
  GH_CMD=("gh" "issue" "create" "--repo" "$REPO" "--title" "$TITLE" "--body-file" "$TMP_BODY_FILE")
  if [[ -n "$TEMPLATE_LABELS" ]]; then
    GH_CMD+=("--label" "$TEMPLATE_LABELS")
  fi

  # Execute and capture output
  ISSUE_URL=$("${GH_CMD[@]}" 2>err.log) || {
    echo "Error creating issue:" >&2
    cat err.log >&2
    rm -f "$TMP_BODY_FILE" err.log
    exit 1
  }

  rm -f "$TMP_BODY_FILE" err.log
  echo "Issue successfully created: $ISSUE_URL"
  exit 0

elif [[ "$SUBCOMMAND" == "backlog-list" ]]; then
  if [[ "$DRY_RUN" == "true" || "$IS_MOCK" == "true" ]]; then
    echo "[DRY RUN / MOCK] Listing open issues for repo: $REPO"
    echo -e "NUMBER\tTITLE\tLABELS\tUPDATED"
    echo -e "1\t[Conception]: Add Scrum Master Script\tconception,enhancement\t2026-06-27"
    echo -e "2\t[Bug]: Setup failure on macOS\tbug\t2026-06-27"
    exit 0
  fi

  gh issue list --repo "$REPO"
  exit 0

elif [[ "$SUBCOMMAND" == "milestone-list" ]]; then
  if [[ "$DRY_RUN" == "true" || "$IS_MOCK" == "true" ]]; then
    echo "[DRY RUN / MOCK] Listing milestones for repo: $REPO"
    echo -e "TITLE\tSTATE\tDUE DATE\tDESCRIPTION"
    echo -e "Sprint 1\topen\t2026-07-15\tInitial Setup"
    exit 0
  fi

  # Query via gh api
  MILESTONES_RAW=$(gh api "repos/$REPO/milestones" --jq '.[] | "\(.title)\t\(.state)\t\(.due_on // "no due date")\t\(.description // "")"' 2>err.log) || {
    echo "Error listing milestones:" >&2
    cat err.log >&2
    rm -f err.log
    exit 1
  }
  rm -f err.log
  
  if [[ -z "$MILESTONES_RAW" ]]; then
    echo "No milestones found."
  else
    echo -e "TITLE\tSTATE\tDUE DATE\tDESCRIPTION"
    echo "$MILESTONES_RAW"
  fi
  exit 0

else
  echo "Error: Unknown subcommand '$SUBCOMMAND'" >&2
  show_help >&2
  exit 1
fi
