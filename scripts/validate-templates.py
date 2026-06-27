#!/usr/bin/env python3
import os
import sys
import unicodedata

# Prohibited AI cliches
CLICHES = [
    "delve",
    "leverage",
    "testament",
    "dive into",
    "feel free",
    "in summary",
    "moreover",
    "firstly",
    "secondly",
    "lastly"
]

# Required keywords per template contract
REQUIRED_KEYWORDS = {
    "prd_contract.md": [
        "Requirements", "User Stories", "Business Value", 
        "Active Requirements", "Scope Boundaries", "High-Level Milestones", 
        "Git Flow", "Conventional Commits"
    ],
    "design_contract.md": [
        "Component Design", "C4", "Mermaid", 
        "Data Flow", "API Schemas", "ADR Mappings", 
        "Git Flow", "Conventional Commits"
    ],
    "qa_report_contract.md": [
        "Test Coverage", "Test Logs", "Unit", "Integration", "E2E", 
        "Backtesting Metrics", "UAT Validation Checklist", 
        "Git Flow", "Conventional Commits"
    ],
    "docs_contract.md": [
        "User Manual", "API Developer Guide", "Business Process Mappings", 
        "Git Flow", "Conventional Commits"
    ],
    "obs_contract.md": [
        "Application Metrics", "Logging Standards", "Tracing Endpoints", 
        "Alert Triggers", "Git Flow", "Conventional Commits"
    ],
    "security_contract.md": [
        "Threat Modeling", "STRIDE", "Dependencies Checking", 
        "Vulnerability Mitigation", "Git Flow", "Conventional Commits"
    ]
}

def has_emoji(text):
    for char in text:
        cp = ord(char)
        # Check standard emoji / symbol blocks
        is_emoji = (0x1F000 <= cp <= 0x1FFFF) or (0x2600 <= cp <= 0x27BF) or (0x2300 <= cp <= 0x23FF)
        if not is_emoji:
            try:
                cat = unicodedata.category(char)
                if cat == 'So':  # Symbol, other
                    is_emoji = True
                else:
                    name = unicodedata.name(char, "").upper()
                    if any(word in name for word in ("EMOJI", "SMILEY", "PICTOGRAPH")):
                        is_emoji = True
            except Exception:
                pass
        if is_emoji:
            return True, char
    return False, None

def validate_template_file(filepath, required_keywords):
    if not os.path.exists(filepath):
        print(f"Error: Template file does not exist: {filepath}")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.strip():
        print(f"Error: Template file is empty: {filepath}")
        return False

    # Check for emojis
    emoji_found, char = has_emoji(content)
    if emoji_found:
        print(f"Error: Emoji or icon '{char}' found in {filepath}. Emojis are strictly prohibited.")
        return False

    # Check for AI cliches
    content_lower = content.lower()
    for cliche in CLICHES:
        if cliche in content_lower:
            print(f"Error: AI cliche '{cliche}' found in {filepath}.")
            return False

    # Check for required keywords
    for keyword in required_keywords:
        if keyword.lower() not in content_lower:
            print(f"Error: Required keyword/phrase '{keyword}' not found in {filepath}.")
            return False

    return True

def main():
    templates_dir = "docs/templates/contracts"
    success = True

    print("Validating Contract Template files...")
    for filename, keywords in REQUIRED_KEYWORDS.items():
        filepath = os.path.join(templates_dir, filename)
        if validate_template_file(filepath, keywords):
            print(f"  {filename} is valid.")
        else:
            success = False

    if success:
        print("\nAll contract templates validation checks passed successfully.")
        sys.exit(0)
    else:
        print("\nContract templates validation failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
