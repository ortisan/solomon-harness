import os
import json
import re
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALLOW_LIST = [
    "Cognitive Load Theory (Sweller)",
    "retrieval practice / testing effect (Roediger and Karpicke)",
    "spacing / distributed practice (Cepeda et al.; Ebbinghaus)",
    "interleaving (Rohrer and Taylor)",
    "dual coding (Paivio)",
    "Bloom's revised taxonomy (Anderson and Krathwohl)",
    "Universal Design for Learning (CAST)",
    "Gagne's nine events of instruction (Gagne)",
    "cognitive theory of multimedia learning (Mayer)",
    "ADDIE (instructional systems design)",
    "backward design / Understanding by Design (Wiggins and McTighe)",
    "constructive alignment (Biggs)",
    "Zone of Proximal Development and scaffolding (Vygotsky; Wood, Bruner and Ross)",
    "stages of cognitive development (Piaget)",
    "ICAP framework (Chi and Wylie)",
    "cognitive apprenticeship (Collins, Brown and Newman)",
    "formative and summative assessment (Scriven; Black and Wiliam)",
    "the power of feedback (Hattie and Timperley)",
    "embedded formative assessment (Wiliam)",
    "analytic and holistic rubrics (Brookhart)",
    "Response to Intervention / MTSS (IES practice guides)",
    "structured literacy / Orton-Gillingham (International Dyslexia Association; National Reading Panel)",
    "concrete-representational-abstract sequence (Bruner)",
    "executive-function / ADHD-aware design (Barkley)"
]

# Extract the methodology names and originator patterns
# Example: "Cognitive Load Theory (Sweller)" -> name: "Cognitive Load Theory", originator: "Sweller"
# For dual coding (Paivio) -> name: "dual coding", originator: "Paivio"
METHODOLOGY_PATTERNS = []
for item in ALLOW_LIST:
    m = re.match(r"^([^(]+)\s*\(([^)]+)\)$", item.strip())
    if m:
        name = m.group(1).strip()
        orig = m.group(2).strip()
        # Create a regex pattern to match both the name and originator, e.g. "Cognitive Load Theory.*Sweller" or similar
        METHODOLOGY_PATTERNS.append((name, orig))


class TestEducationalPsychologist(unittest.TestCase):

    def setUp(self):
        self.agent_dir = os.path.join(WORKSPACE, "agents", "educational_psychologist")
        self.skills_dir = os.path.join(self.agent_dir, "skills")

    def test_folder_structure_and_config(self):
        self.assertTrue(os.path.isdir(self.agent_dir), f"Directory {self.agent_dir} does not exist")
        
        persona_path = os.path.join(self.agent_dir, "persona.md")
        self.assertTrue(os.path.isfile(persona_path), "persona.md is missing")
        
        profile_path = os.path.join(self.agent_dir, "agents", "educational_psychologist.md")
        self.assertTrue(os.path.isfile(profile_path), "agents/educational_psychologist.md is missing")
        
        config_path = os.path.join(self.agent_dir, ".agent", "config.json")
        self.assertTrue(os.path.isfile(config_path), ".agent/config.json is missing")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.assertEqual(config.get("agent_name"), "educational_psychologist")

    def test_skills_files_and_attributions(self):
        self.assertTrue(os.path.isdir(self.skills_dir), f"Directory {self.skills_dir} does not exist")
        
        skill_files = []
        for name in os.listdir(self.skills_dir):
            path = os.path.join(self.skills_dir, name)
            if os.path.isfile(path) and not name.startswith('.'):
                self.assertTrue(re.match(r"^[a-z0-9]+(_[a-z0-9]+)*\.md$", name), f"Invalid skill name format: {name}")
                skill_files.append(name)
                
        self.assertGreaterEqual(len(skill_files), 9, f"Expected at least 9 skills files, found {len(skill_files)}")
        
        exempt_files = {"definition_of_done.md", "common_pitfalls.md", "scope_and_non_negotiables.md"}
        domain_skills = [f for f in skill_files if f not in exempt_files]
        
        self.assertEqual(len(skill_files) - len(domain_skills), 3, "Missing some exempt files or extra files classified as exempt")
        self.assertEqual(set(skill_files) & exempt_files, exempt_files, f"Exempt files must be exactly {exempt_files}")
        
        # Check methodologies and originators
        matching_skills_count = 0
        sourcing_skill_present = False
        
        for skill_file in domain_skills:
            path = os.path.join(self.skills_dir, skill_file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            has_attribution = False
            for name, orig in METHODOLOGY_PATTERNS:
                # Search for attribution in content, e.g. "dual coding (Paivio)" or "Cognitive Load Theory (Sweller)"
                # Let's search case insensitively or with exact text. The spec says e.g. "Cognitive Load Theory (Sweller)"
                # Let's make it a case-insensitive check but look for both the methodology name and parenthesized originator.
                pattern = rf"{re.escape(name)}\s*\([^)]*{re.escape(orig)}[^)]*\)"
                if re.search(pattern, content, re.IGNORECASE):
                    has_attribution = True
                    break
                    
            if has_attribution:
                matching_skills_count += 1
                
            if skill_file == "evidence_based_sourcing.md":
                sourcing_skill_present = True
                self.assertIn("Pashler", content, "evidence_based_sourcing.md must contain 'Pashler'")
                self.assertTrue(re.search(r"\b\d{4}\b", content), "evidence_based_sourcing.md must contain a four-digit year")
                self.assertIn("learning-styles", content, "evidence_based_sourcing.md must contain 'learning-styles'")
                self.assertTrue("fad" in content.lower() or "reject" in content.lower(), "evidence_based_sourcing.md must define a fad-rejection criterion")
                
        self.assertGreaterEqual(matching_skills_count, 6, f"Expected at least 6 domain skills with methodology attributions, found {matching_skills_count}")
        self.assertTrue(sourcing_skill_present, "evidence_based_sourcing.md is missing from domain skills")

    def test_cross_cutting_summaries(self):
        exempt_files = ["definition_of_done.md", "common_pitfalls.md", "scope_and_non_negotiables.md"]
        for name in exempt_files:
            path = os.path.join(self.skills_dir, name)
            self.assertTrue(os.path.isfile(path), f"{name} is missing")
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            self.assertTrue(len(lines) > 0, f"{name} is empty")
            # First non-empty line (excluding markdown headers) must be a single-sentence summary
            first_para = ""
            for line in lines:
                if not line.startswith("#"):
                    first_para = line
                    break
            self.assertTrue(first_para.endswith("."), f"First paragraph of {name} must be a single-sentence summary ending with a period")


if __name__ == "__main__":
    unittest.main()
