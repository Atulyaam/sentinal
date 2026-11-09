"""Validator script for Kiro Crew App manifest (app.json) and packaged assets."""

import json
import re
import sys
from pathlib import Path

REQUIRED_ROOT_FIELDS = [
    "name",
    "version",
    "displayName",
    "description",
    "author",
    "license",
    "minKiroCrewVersion",
    "iconPath",
    "agents",
    "skills",
    "ui",
    "permissions",
]

REQUIRED_AGENT_FIELDS = ["name", "displayName", "model", "prompt"]


def validate_manifest(app_dir: Path) -> bool:
    manifest_path = app_dir / "app.json"
    print(f"[*] Validating Kiro Crew manifest at: {manifest_path}")

    if not manifest_path.exists():
        print(f"[!] Manifest not found: {manifest_path}", file=sys.stderr)
        return False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        print(f"[!] Failed to parse JSON: {exc}", file=sys.stderr)
        return False

    errors = []

    # Check root fields
    for field in REQUIRED_ROOT_FIELDS:
        if field not in manifest:
            errors.append(f"Missing required manifest field: '{field}'")

    # Validate UI section
    ui = manifest.get("ui", {})
    if not isinstance(ui, dict):
        errors.append("'ui' field must be an object")
    else:
        entry = ui.get("entry")
        if not entry or not isinstance(entry, str):
            errors.append("'ui.entry' must be a valid path string (e.g. 'dist/index.mjs')")
        else:
            entry_path = app_dir / entry
            if not entry_path.exists():
                errors.append(f"Referenced ui.entry does not exist on disk: {entry_path}")

        pages = ui.get("pages")
        if not isinstance(pages, list) or len(pages) == 0:
            errors.append("'ui.pages' must be a non-empty array of page routes")
        else:
            for i, page in enumerate(pages):
                if not page.get("route"):
                    errors.append(f"ui.pages[{i}] missing 'route'")
                if not page.get("label"):
                    errors.append(f"ui.pages[{i}] missing 'label'")

    # Validate permissions section
    permissions = manifest.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append("'permissions' field must be an object")
    else:
        api_perms = permissions.get("api")
        if not isinstance(api_perms, list) or len(api_perms) == 0:
            errors.append("'permissions.api' must be a non-empty array of allowed API routes")

    # Validate icon
    icon_path = app_dir / manifest.get("iconPath", "")
    if not icon_path.exists():
        errors.append(f"Referenced iconPath does not exist: {icon_path}")

    # Validate agent definitions
    for agent_rel in manifest.get("agents", []):
        agent_path = app_dir / agent_rel
        if not agent_path.exists():
            errors.append(f"Referenced agent file does not exist: {agent_path}")
        else:
            try:
                with open(agent_path, "r", encoding="utf-8") as af:
                    agent_data = json.load(af)
                for req_f in REQUIRED_AGENT_FIELDS:
                    if req_f not in agent_data:
                        errors.append(f"Agent '{agent_rel}' missing required field: '{req_f}'")
            except Exception as e:
                errors.append(f"Agent '{agent_rel}' is not valid JSON: {e}")

    # Validate skills
    for skill_rel in manifest.get("skills", []):
        skill_dir = app_dir / skill_rel
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"Referenced skill directory missing SKILL.md: {skill_md}")
        else:
            try:
                content = skill_md.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    errors.append(f"Skill '{skill_rel}/SKILL.md' missing YAML frontmatter ('---')")
                else:
                    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                    if not frontmatter_match:
                        errors.append(f"Skill '{skill_rel}/SKILL.md' has unclosed YAML frontmatter")
                    else:
                        fm = frontmatter_match.group(1)
                        if "name:" not in fm or "description:" not in fm:
                            errors.append(f"Skill '{skill_rel}/SKILL.md' frontmatter missing 'name:' or 'description:'")
            except Exception as e:
                errors.append(f"Failed to read skill '{skill_rel}/SKILL.md': {e}")

    if errors:
        print(f"[X] Manifest validation FAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"    - {err}", file=sys.stderr)
        return False

    print("[+] Kiro Crew manifest is VALID and all resource references exist!")
    print(f"    - App Name: {manifest.get('name')}")
    print(f"    - Display Name: {manifest.get('displayName')}")
    print(f"    - Version: {manifest.get('version')}")
    print(f"    - UI Entry: {ui.get('entry')} (verified present on disk)")
    print(f"    - Registered Agents: {manifest.get('agents')} (verified schema)")
    print(f"    - Registered Skills: {manifest.get('skills')} (verified frontmatter)")
    return True


if __name__ == "__main__":
    app_directory = Path(__file__).resolve().parent.parent / "apps" / "crew-app"
    success = validate_manifest(app_directory)
    sys.exit(0 if success else 1)
