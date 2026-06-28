import os
import re

# Leading list or checkbox markers to drop from a skill's first line, e.g.
# "- ", "* ", "+ ", "- [ ] ", "- [x] ".
_MARKER_RE = re.compile(r"^\s*[-*+]\s+(\[[ xX]\]\s+)?")

# Maximum length of a derived description before it is hard-truncated.
_PURPOSE_LIMIT = 140

# How many body lines to scan when looking for an explicit "Purpose:" line.
_PURPOSE_SCAN_LINES = 15


def _strip_marker(text):
    """Remove a leading list or checkbox marker from a line."""
    return _MARKER_RE.sub("", text)


def _summarize(text):
    """Turn a raw skill line into a clean one-line description.

    Collapses internal whitespace, drops any leading list marker, and caps the
    result at the first sentence or ``_PURPOSE_LIMIT`` characters (whichever is
    shorter), trimming at a word boundary and appending a single ellipsis only
    when the text was hard-truncated.
    """
    text = re.sub(r"\s+", " ", _strip_marker(text)).strip()
    if not text:
        return ""
    match = re.search(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) <= _PURPOSE_LIMIT:
        return sentence
    cut = text[:_PURPOSE_LIMIT].rstrip()
    if " " in cut:
        cut = cut[: cut.rfind(" ")].rstrip()
    return cut + "…"


def extract_metadata(skill_path):
    title = ""
    purpose = ""
    first_body = ""
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        body_seen = 0
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("#"):
                if not title and (line_str.startswith("# ") or line_str.startswith("## ")):
                    title = line_str.lstrip("#").strip()
                continue
            candidate = _strip_marker(line_str)
            if candidate.lower().startswith("purpose:"):
                purpose = candidate[len("purpose:"):].strip()
                break
            if not first_body:
                first_body = candidate
            body_seen += 1
            if body_seen >= _PURPOSE_SCAN_LINES:
                break
        purpose = _summarize(purpose or first_body)
    except Exception:
        purpose = ""
    return title or os.path.basename(skill_path)[:-3], purpose or "No description provided."

def document_agent(agent_name, agents_dir):
    agent_dir = os.path.join(agents_dir, agent_name)
    skills_dir = os.path.join(agent_dir, "skills")
    profile_path = os.path.join(agent_dir, "agents", f"{agent_name}.md")
    
    if not os.path.isfile(profile_path):
        return

    skills_list = []
    if os.path.isdir(skills_dir):
        for filename in sorted(os.listdir(skills_dir)):
            if filename.endswith(".md"):
                file_path = os.path.join(skills_dir, filename)
                title, purpose = extract_metadata(file_path)
                skills_list.append((filename[:-3], filename, purpose))

    skills_block = "## Active Skills\n\n"
    if skills_list:
        skills_block += "The following specific skills are actively configured for this agent:\n"
        for slug, fname, purpose in skills_list:
            skills_block += f"- [{slug}](skills/{fname}) — {purpose}\n"
    else:
        skills_block += "No local skills configured.\n"

    skills_block += "\n## External Skills\n\n"
    skills_block += "Additional skills can be fetched and integrated from external skill servers at any time. Configure external repositories in `skill-sources.json` and use:\n"
    skills_block += "```bash\n"
    skills_block += f"solomon-harness skills add <source> <skill> --agent {agent_name}\n"
    skills_block += "```\n"

    with open(profile_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "<!-- BEST_PRACTICES_APPENDED_START -->"
    appended_part = ""
    if marker in content:
        parts = content.split(marker)
        content = parts[0]
        appended_part = marker + parts[1]

    # Strip existing Active Skills and External Skills sections to allow updates
    content = re.split(r'^##\s+Active Skills', content, flags=re.MULTILINE)[0]
    content = re.split(r'^##\s+External Skills', content, flags=re.MULTILINE)[0]
    content = content.rstrip()

    new_content = f"{content}\n\n{skills_block}\n"
    if appended_part:
        new_content += appended_part

    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Documented {agent_name} successfully.")

def main():
    # The script lives in scripts/, so the repo root is its parent's parent.
    # Resolving from __file__ makes this work regardless of the current
    # working directory.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agents_dir = os.path.join(repo_root, "agents")
    if not os.path.isdir(agents_dir):
        agents_dir = "agents"
    for item in os.listdir(agents_dir):
        agent_path = os.path.join(agents_dir, item)
        if os.path.isdir(agent_path) and os.path.isdir(os.path.join(agent_path, "agents")):
            document_agent(item, agents_dir)

if __name__ == "__main__":
    main()
