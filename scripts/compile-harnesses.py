#!/usr/bin/env python3
"""
Solomon Harness Compiler Script
Scans the agents/ directory for agent definitions and compiles their harnesses from templates.
"""

import os
import sys
import shutil
import logging

# Configure logging with direct, professional English format and no emojis
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("harness_compiler")


def compile_harnesses(workspace_root: str):
    """
    Compiles agent harnesses for all discovered agents in the workspace.
    """
    agents_dir = os.path.join(workspace_root, "agents")
    templates_dir = os.path.join(workspace_root, "templates", "harness")

    if not os.path.isdir(agents_dir):
        logger.error(f"Agents root directory not found at: {agents_dir}")
        sys.exit(1)

    if not os.path.isdir(templates_dir):
        logger.error(f"Templates harness directory not found at: {templates_dir}")
        sys.exit(1)

    global_agents_md = os.path.join(agents_dir, "AGENTS.md")
    if not os.path.isfile(global_agents_md):
        logger.error(f"Global AGENTS.md rules file not found at: {global_agents_md}")
        sys.exit(1)

    # Load dynamic pattern configurations from global config
    global_config_path = os.path.join(workspace_root, ".agent", "config.json")
    architecture_pattern = None
    observability_pattern = None
    security_pattern = None
    if os.path.isfile(global_config_path):
        try:
            import json
            with open(global_config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            architecture_pattern = config_data.get("architecture_pattern")
            observability_pattern = config_data.get("observability_pattern")
            security_pattern = config_data.get("security_pattern")
            logger.info("Loaded dynamic pattern settings from global configuration.")
        except Exception as e:
            logger.warning(f"Failed to read global configuration at {global_config_path}: {e}")

    # 1. Discover active agent specialists
    logger.info("Scanning for active agent specialists...")
    agent_names = set()
    
    # Iterate over immediate children of the agents directory
    for item in os.listdir(agents_dir):
        item_path = os.path.join(agents_dir, item)
        # Discover from flat markdown files
        if os.path.isfile(item_path) and item.endswith(".md") and item != "AGENTS.md":
            agent_names.add(item[:-3])
        # Discover from nested compiled subdirectories
        elif os.path.isdir(item_path):
            nested_md = os.path.join(item_path, "agents", f"{item}.md")
            if os.path.isfile(nested_md):
                agent_names.add(item)

    sorted_agent_names = sorted(list(agent_names))
    logger.info(f"Discovered {len(sorted_agent_names)} agents: {', '.join(sorted_agent_names)}")

    # 2. Compile each agent's harness
    for agent_name in sorted_agent_names:
        logger.info(f"Compiling harness for agent: {agent_name}")
        
        # Determine the source of truth for the agent prompt markdown
        source_agent_md = os.path.join(agents_dir, f"{agent_name}.md")
        nested_agent_md = os.path.join(agents_dir, agent_name, "agents", f"{agent_name}.md")
        
        agent_md_content = None
        if os.path.isfile(source_agent_md):
            try:
                with open(source_agent_md, "r", encoding="utf-8") as f:
                    agent_md_content = f.read()
            except Exception as e:
                logger.error(f"Failed to read source agent file {source_agent_md}: {e}")
                sys.exit(1)
        elif os.path.isfile(nested_agent_md):
            try:
                with open(nested_agent_md, "r", encoding="utf-8") as f:
                    agent_md_content = f.read()
            except Exception as e:
                logger.error(f"Failed to read nested agent file {nested_agent_md}: {e}")
                sys.exit(1)
        else:
            logger.error(f"No source markdown found for agent: {agent_name}")
            sys.exit(1)

        # Strip any previously appended best practices to prevent double appends
        marker = "<!-- BEST_PRACTICES_APPENDED_START -->"
        if marker in agent_md_content:
            agent_md_content = agent_md_content.split(marker)[0]
        agent_md_content = agent_md_content.rstrip()

        # Build dynamic best practice blocks to append
        blocks = []
        
        # Check architecture patterns
        if agent_name in ["software_architect", "software_engineer", "qa", "sre"]:
            if architecture_pattern and str(architecture_pattern).lower() != "none":
                arch_path = os.path.join(
                    workspace_root,
                    "templates",
                    "patterns",
                    "architecture",
                    f"{architecture_pattern}.md",
                )
                if os.path.isfile(arch_path):
                    try:
                        with open(arch_path, "r", encoding="utf-8") as f:
                            blocks.append(f.read().strip())
                        logger.info(
                            f"Applying architecture pattern '{architecture_pattern}' to {agent_name}..."
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to read architecture pattern file {arch_path}: {e}"
                        )
                        sys.exit(1)
                else:
                    logger.error(
                        f"Architecture pattern file not found at: {arch_path}"
                    )
                    sys.exit(1)

        # Check observability patterns
        if agent_name in ["observability", "software_engineer", "sre"]:
            if observability_pattern == "opentelemetry":
                obs_path = os.path.join(
                    workspace_root,
                    "templates",
                    "patterns",
                    "observability",
                    "opentelemetry.md",
                )
                if os.path.isfile(obs_path):
                    try:
                        with open(obs_path, "r", encoding="utf-8") as f:
                            blocks.append(f.read().strip())
                        logger.info(
                            f"Applying observability pattern 'opentelemetry' to {agent_name}..."
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to read observability pattern file {obs_path}: {e}"
                        )
                        sys.exit(1)
                else:
                    logger.error(
                        f"Observability pattern file not found at: {obs_path}"
                    )
                    sys.exit(1)

        # Check security patterns
        if agent_name in ["security", "software_engineer", "qa", "sre"]:
            if security_pattern == "secure_dev":
                sec_path = os.path.join(
                    workspace_root,
                    "templates",
                    "patterns",
                    "security",
                    "secure_dev.md",
                )
                if os.path.isfile(sec_path):
                    try:
                        with open(sec_path, "r", encoding="utf-8") as f:
                            blocks.append(f.read().strip())
                        logger.info(
                            f"Applying security pattern 'secure_dev' to {agent_name}..."
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to read security pattern file {sec_path}: {e}"
                        )
                        sys.exit(1)
                else:
                    logger.error(f"Security pattern file not found at: {sec_path}")
                    sys.exit(1)

        if blocks:
            agent_md_content = (
                agent_md_content.rstrip()
                + "\n\n"
                + marker
                + "\n\n"
                + "\n\n".join(blocks)
                + "\n"
            )
            
        target_agent_dir = os.path.join(agents_dir, agent_name)
        
        # Clean target directory if it already exists to ensure a fresh compilation
        if os.path.exists(target_agent_dir):
            logger.info(f"Cleaning existing directory for {agent_name}...")
            try:
                if os.path.isdir(target_agent_dir):
                    shutil.rmtree(target_agent_dir)
                else:
                    os.remove(target_agent_dir)
            except Exception as e:
                logger.error(f"Failed to clean target directory {target_agent_dir}: {e}")
                sys.exit(1)

        # Copy all directories and files from templates/harness/ to agents/<agent_name>/
        logger.info(f"Copying harness templates to {target_agent_dir}...")
        try:
            shutil.copytree(templates_dir, target_agent_dir)
        except Exception as e:
            logger.error(f"Failed to copy templates to {target_agent_dir}: {e}")
            sys.exit(1)

        # Replace placeholder {{AGENT_NAME}} in config.json
        config_path = os.path.join(target_agent_dir, ".agent", "config.json")
        if os.path.isfile(config_path):
            logger.info(f"Replacing config placeholder for {agent_name}...")
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                content = content.replace("{{AGENT_NAME}}", agent_name)
                
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to update config.json for {agent_name}: {e}")
                sys.exit(1)
        else:
            logger.warning(f"config.json not found at {config_path} for agent: {agent_name}")

        # Create target agent's internal agents/ subdirectory
        target_sub_agents_dir = os.path.join(target_agent_dir, "agents")
        logger.info(f"Creating internal agents directory for {agent_name}...")
        try:
            os.makedirs(target_sub_agents_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create agents/ directory for {agent_name}: {e}")
            sys.exit(1)

        # Copy global rules to agents/<agent_name>/agents/AGENTS.md
        logger.info(f"Copying global rules to {agent_name} harness...")
        try:
            shutil.copy2(global_agents_md, os.path.join(target_sub_agents_dir, "AGENTS.md"))
        except Exception as e:
            logger.error(f"Failed to copy AGENTS.md for {agent_name}: {e}")
            sys.exit(1)

        # Copy specific agent markdown to agents/<agent_name>/agents/<agent_name>.md
        dest_agent_md = os.path.join(target_sub_agents_dir, f"{agent_name}.md")
        logger.info(f"Copying specialist prompt definition for {agent_name}...")
        try:
            with open(dest_agent_md, "w", encoding="utf-8") as f:
                f.write(agent_md_content)
        except Exception as e:
            logger.error(f"Failed to write agent prompt file for {agent_name}: {e}")
            sys.exit(1)

    logger.info("Compilation completed successfully.")


if __name__ == "__main__":
    # Get workspace root relative to script execution context, defaulting to current working directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_workspace_root = os.path.abspath(os.path.join(script_dir, ".."))
    
    compile_harnesses(default_workspace_root)
