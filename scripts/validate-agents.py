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
    "lastly",
]

# Required keywords per profile
REQUIRED_KEYWORDS = {
    "practice_curator.md": [
        "Practice Curator",
        "best practices",
        "state of the art",
        "benchmark",
        "gap report",
        "reviewed",
        "sources",
    ],
    "product_owner.md": [
        "Product Owner",
        "Product Requirements Document",
        "PRD",
        "specifications",
        "deliverables",
    ],
    "scrum_master.md": [
        "Scrum Master",
        "milestones",
        "backlog",
        "sprint",
        "sprint planning",
        "status meetings",
        "develop",
        "feature/*",
        "release/*",
        "conventional commit",
    ],
    "software_architect.md": [
        "Software Architect",
        "C4",
        "Architectural Decision Record",
        "ADR",
        "Design Contract",
    ],
    "software_engineer.md": [
        "Software Engineer",
        "TDD",
        "Test-Driven Development",
        "clean code",
        "debugging",
        "feature/*",
        "bugfix/*",
        "conventional commit",
    ],
    "ml_engineer.md": [
        "ML Engineer",
        "hyperparameters",
        "validation",
        "dataset",
        "features",
    ],
    "quant_trader.md": [
        "Quant Trader",
        "backtest",
        "slippage",
        "transaction costs",
        "risk parameters",
    ],
    "qa.md": [
        "QA Specialist",
        "UAT",
        "User Acceptance Testing",
        "verification",
        "QA Report",
        "feature/*",
        "develop",
        "release/*",
        "production",
    ],
    "documenter.md": [
        "Documenter",
        "business value",
        "technical manuals",
        "design documentation",
        "user guides",
    ],
    "observability.md": [
        "Observability Specialist",
        "log diagnostics",
        "metrics tracking",
        "performance profiling",
        "monitoring dashboards",
    ],
    "security.md": [
        "Security Specialist",
        "threat modeling",
        "SAST",
        "vulnerability checks",
        "dependencies",
    ],
    "flutter.md": [
        "Flutter Specialist",
        "Dart",
        "clean architecture",
        "responsive layouts",
        "widget trees",
        "state management",
        "widget/integration testing",
        "Git Flow",
        "Conventional Commits",
    ],
    "frontend.md": [
        "Frontend React & Angular Specialist",
        "React",
        "Angular",
        "hooks",
        "components",
        "state management",
        "design tokens",
        "Git Flow",
        "Conventional Commits",
    ],
    "sre.md": [
        "SRE Specialist",
        "high availability",
        "infrastructure",
        "deployment pipelines",
        "load testing",
        "incident runbooks",
        "disaster recovery",
        "SLA/SLO",
        "Git Flow",
        "Conventional Commits",
    ],
    "seo.md": [
        "SEO Specialist",
        "semantic hierarchy",
        "metadata",
        "indexing/crawling",
        "page speed",
        "audits",
        "Git Flow",
        "Conventional Commits",
    ],
    "auth_engineer.md": [
        "Auth Engineer",
        "Authentication",
        "Authorization",
        "OAuth",
        "OpenID Connect",
        "social login",
        "RBAC",
        "MFA",
        "session",
    ],
    "android.md": [
        "Android Specialist",
        "Kotlin",
        "Jetpack Compose",
        "Coroutines",
        "MVVM",
        "Gradle",
        "instrumentation",
        "Material Design",
    ],
    "apple.md": [
        "Apple Specialist",
        "Swift",
        "SwiftUI",
        "UIKit",
        "Swift Concurrency",
        "Combine",
        "Xcode",
        "XCTest",
        "MVVM",
    ],
    "dba.md": [
        "Database Administrator",
        "data models",
        "performance audits",
        "index",
        "migration",
    ],
    "data_analyst.md": [
        "Data Analyst",
        "clean incoming",
        "SQL",
        "big data",
        "visualization",
    ],
    "data_science.md": [
        "Data Scientist",
        "predictive",
        "statistical",
        "didactically",
        "cross-validation",
    ],
}


def has_emoji(text):
    for char in text:
        cp = ord(char)
        # Check standard emoji / symbol blocks
        is_emoji = (
            (0x1F000 <= cp <= 0x1FFFF)
            or (0x2600 <= cp <= 0x27BF)
            or (0x2300 <= cp <= 0x23FF)
        )
        if not is_emoji:
            try:
                cat = unicodedata.category(char)
                if cat == "So":  # Symbol, other
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


def validate_agent_file(filepath, required_keywords):
    if not os.path.exists(filepath):
        print(f"Error: Agent file does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print(f"Error: Agent file is empty: {filepath}")
        return False

    # Check for emojis
    emoji_found, char = has_emoji(content)
    if emoji_found:
        print(
            f"Error: Emoji or icon '{char}' found in {filepath}. Emojis are strictly prohibited."
        )
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
            print(
                f"Error: Required keyword/phrase '{keyword}' not found in {filepath}."
            )
            return False

    return True


def main():
    agents_dir = "agents"
    success = True

    print("Validating Agent Profile files...")
    for filename, keywords in REQUIRED_KEYWORDS.items():
        agent_name = filename[:-3]
        filepath = os.path.join(agents_dir, agent_name, "agents", filename)
        if validate_agent_file(filepath, keywords):
            print(f"  {filename} is valid.")
        else:
            success = False

    if success:
        print("\nAll agent profile validation checks passed successfully.")
        sys.exit(0)
    else:
        print("\nAgent profile validation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
