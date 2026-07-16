"""Role/project template distribution.

A *template* is a curated bundle of agent resources (MCP services, Claude
skills, instruction files, permissions/hooks) stored as files in a Unity
Catalog Volume. `ucode configure` fetches the template(s) that apply to a user
— chosen explicitly (``--template``/``--role``) or auto-detected from SCIM group
membership — composes them, and applies them to the configured agents.

Governance is Databricks-native: the UC READ grant on a template's Volume path
(tied to a SCIM group) decides who can fetch it, and the UC grants on the MCP
services / models it references decide what actually registers. ucode adds no
access-control layer of its own; a resource the user's token can't see just
soft-fails with a warning.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ucode.config_io import backup_existing_file, deep_merge_dict
from ucode.databricks import (
    get_current_user_groups,
    list_volume_dir,
    read_volume_file,
)
from ucode.ui import print_note, print_success, print_warning, spinner

# Default template store. Overridable via `ucode configure --templates-volume`.
# A Suffolk deployment points this at its governed catalog, e.g.
# `/Volumes/business_functions/ucode/templates`.
DEFAULT_TEMPLATES_VOLUME = "/Volumes/business_functions/ucode/templates"

INDEX_FILENAME = "index.json"
TEMPLATE_FILENAME = "template.json"

# ~/.claude/skills/<name>/ is where Claude Code discovers user skills. Instruction
# files land at ~/.claude/CLAUDE.md. Both are backed up before ucode overwrites.
CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_SKILLS_DIR = CLAUDE_DIR / "skills"
CLAUDE_INSTRUCTIONS_PATH = CLAUDE_DIR / "CLAUDE.md"


@dataclass
class TemplateManifest:
    """One template bundle, parsed from a Volume ``template.json``.

    ``extends`` names other templates whose resources are merged in first (this
    template wins on conflicting leaves). All Volume paths in ``skills`` /
    ``instructions`` are relative to the template's own directory."""

    name: str
    description: str = ""
    extends: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    mcp_services: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    instructions: dict[str, str] = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)
    hooks: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> TemplateManifest:
        # The template's own directory (= its `name`) qualifies every relative
        # Volume path it declares, so after composition (which unions resources
        # from this template AND its `extends` parents) each skill/instruction
        # path still points at the right template dir under base_path.
        dir_name = str(data.get("name") or name)
        # Coerce list/dict fields defensively via a local helper so the checker
        # sees concrete types (and a scalar where a list is expected, e.g.
        # `"skills": "x"`, is dropped rather than iterated char-by-char).
        mcp = _as_dict(data.get("mcp"))
        services = _as_list(mcp.get("services"))
        raw_extends = _as_list(data.get("extends"))
        raw_agents = _as_list(data.get("agents"))
        raw_skills = _as_list(data.get("skills"))
        raw_instructions = _as_dict(data.get("instructions"))
        return cls(
            name=dir_name,
            description=str(data.get("description") or ""),
            extends=[s for s in raw_extends if isinstance(s, str)],
            agents=[s for s in raw_agents if isinstance(s, str)],
            mcp_services=[s for s in services if isinstance(s, str) and s.strip()],
            skills=[_join(dir_name, s) for s in raw_skills if isinstance(s, str) and s.strip()],
            instructions={
                k: _join(dir_name, v)
                for k, v in raw_instructions.items()
                if isinstance(k, str) and isinstance(v, str) and v.strip()
            },
            permissions=_as_dict(data.get("permissions")),
            hooks=_as_dict(data.get("hooks")),
        )


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _join(base_path: str, *parts: str) -> str:
    """Join Volume path segments with single slashes, no trailing slash."""
    segments = [base_path.rstrip("/")]
    segments.extend(part.strip("/") for part in parts)
    return "/".join(segments)


def fetch_index(workspace: str, token: str, base_path: str) -> dict:
    """Read and parse ``index.json`` (SCIM group -> [template, ...] mapping).

    Raises RuntimeError if it can't be read or isn't a JSON object — a missing
    index is a deployment error worth surfacing, not something to swallow."""
    text = read_volume_file(workspace, token, _join(base_path, INDEX_FILENAME))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Template index `{INDEX_FILENAME}` is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Template index `{INDEX_FILENAME}` must be a JSON object.")
    return data


def fetch_template(workspace: str, token: str, base_path: str, name: str) -> TemplateManifest:
    """Read and parse ``<base_path>/<name>/template.json`` into a manifest."""
    text = read_volume_file(workspace, token, _join(base_path, name, TEMPLATE_FILENAME))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Template `{name}` is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Template `{name}` must be a JSON object.")
    return TemplateManifest.from_dict(name, data)


def _merge_permissions(base: dict, overlay: dict) -> dict:
    """Deep-merge two permissions blocks, UNIONing the allow/deny lists.

    A plain deep-merge would let the overlay's list replace the base's; for
    allow/deny we want the union so an extended template can only *add* rules,
    never silently drop a shared one."""
    merged = deep_merge_dict(dict(base), overlay)
    for key in ("allow", "deny", "ask"):
        base_list = _as_list(base.get(key))
        overlay_list = _as_list(overlay.get(key))
        if base_list or overlay_list:
            merged[key] = base_list + [r for r in overlay_list if r not in base_list]
    return merged


def compose(manifests: list[TemplateManifest]) -> TemplateManifest:
    """Merge an ordered list of manifests into one (later entries win).

    MCP services and skills are unioned (order preserved, deduped); instructions
    and hooks deep-merge (later wins per key); permissions union their allow/deny
    lists. ``extends`` must already be flattened into the input order by
    :func:`load_composed`."""
    if not manifests:
        raise RuntimeError("compose() requires at least one manifest.")
    services: list[str] = []
    skills: list[str] = []
    agents: list[str] = []
    instructions: dict[str, str] = {}
    permissions: dict = {}
    hooks: dict = {}
    for m in manifests:
        for svc in m.mcp_services:
            if svc not in services:
                services.append(svc)
        for skill in m.skills:
            if skill not in skills:
                skills.append(skill)
        for agent in m.agents:
            if agent not in agents:
                agents.append(agent)
        instructions.update(m.instructions)
        permissions = _merge_permissions(permissions, m.permissions)
        hooks = deep_merge_dict(hooks, m.hooks)
    return TemplateManifest(
        name="+".join(m.name for m in manifests),
        description=manifests[-1].description,
        agents=agents,
        mcp_services=services,
        skills=skills,
        instructions=instructions,
        permissions=permissions,
        hooks=hooks,
    )


def load_composed(workspace: str, token: str, base_path: str, names: list[str]) -> TemplateManifest:
    """Fetch ``names`` and all templates they ``extends`` (transitively), then
    compose them so dependencies merge before dependents and later names win.

    Cycles and repeats are handled: each template is fetched once, and a
    template appears in the merge order after everything it extends."""
    cache: dict[str, TemplateManifest] = {}
    order: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in cache:
            if name not in order:
                order.append(name)
            return
        if name in visiting:
            # Cycle — skip re-entry; the template still lands in `order` once
            # its first visit completes.
            return
        visiting.add(name)
        manifest = fetch_template(workspace, token, base_path, name)
        cache[name] = manifest
        for parent in manifest.extends:
            visit(parent)
        visiting.discard(name)
        if name not in order:
            order.append(name)

    for name in names:
        visit(name)
    return compose([cache[name] for name in order])


def resolve_template_names(
    workspace: str,
    token: str,
    base_path: str,
    explicit: list[str] | None,
) -> list[str]:
    """Decide which templates apply (hybrid selection).

    1. ``explicit`` (``--template``/``--role``) — used verbatim, SCIM skipped.
    2. else the union of templates mapped to the user's SCIM groups in
       ``index.json``.
    3. else ``index.json``'s ``default`` list.

    Returns [] only when there is genuinely nothing to apply (no explicit
    choice, no group match, no default)."""
    if explicit:
        return list(dict.fromkeys(explicit))

    index = fetch_index(workspace, token, base_path)
    group_map = _as_dict(index.get("groups"))
    default = [s for s in _as_list(index.get("default")) if isinstance(s, str)]

    with spinner("Detecting your Databricks groups..."):
        groups = get_current_user_groups(workspace, token)

    selected: list[str] = []
    for group in groups:
        mapped = group_map.get(group)
        if isinstance(mapped, list):
            for name in mapped:
                if isinstance(name, str) and name not in selected:
                    selected.append(name)
    if selected:
        matched_groups = [g for g in groups if g in group_map]
        print_note(f"Matched group(s): {', '.join(matched_groups)}")
        return selected

    if groups:
        print_note("No configured template matched your groups; using the default template.")
    return list(dict.fromkeys(default))


# ── Resource writers (net-new: ucode wrote no skills/instructions before) ──


def _copy_volume_tree(
    workspace: str, token: str, src_volume_path: str, dest_dir: Path
) -> list[Path]:
    """Recursively copy a Volume directory into ``dest_dir``.

    Returns the list of files written (for revert tracking). Raises RuntimeError
    if the source can't be listed/read."""
    written: list[Path] = []
    entries = list_volume_dir(workspace, token, src_volume_path)
    for entry in entries:
        name = entry.get("name") or Path(str(entry.get("path"))).name
        path = str(entry.get("path"))
        dest = dest_dir / name
        if entry.get("is_directory"):
            written.extend(_copy_volume_tree(workspace, token, path, dest))
        else:
            content = read_volume_file(workspace, token, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            written.append(dest)
    return written


def apply_skills(
    workspace: str, token: str, base_path: str, manifest: TemplateManifest
) -> list[str]:
    """Copy each skill directory referenced by the manifest into
    ``~/.claude/skills/<skill-name>/``. Returns the destination skill dirs
    written (absolute paths as strings) so ``ucode revert`` can remove them."""
    written_dirs: list[str] = []
    for rel in manifest.skills:
        # `rel` is relative to the composing template's dir; but skills are
        # unioned across templates, so we resolve against base_path/<template>.
        # A skill entry is stored as "<template>/skills/<name>" so it's fully
        # qualified from base_path.
        src = _join(base_path, rel)
        skill_name = Path(rel).name
        dest = CLAUDE_SKILLS_DIR / skill_name
        try:
            files = _copy_volume_tree(workspace, token, src, dest)
        except RuntimeError as exc:
            print_warning(f"Skipped skill `{skill_name}`: {exc}")
            continue
        if files:
            written_dirs.append(str(dest))
            print_success(f"Installed skill `{skill_name}` ({len(files)} file(s))")
    return written_dirs


def apply_instructions(
    workspace: str, token: str, base_path: str, manifest: TemplateManifest
) -> str | None:
    """Write the composed Claude instruction file to ``~/.claude/CLAUDE.md``,
    backing up any existing file first. Returns the destination path written, or
    None if the manifest has no Claude instructions.

    Instruction values are Volume paths relative to ``base_path`` (fully
    qualified as ``<template>/instructions/<file>``)."""
    rel = manifest.instructions.get("claude")
    if not rel:
        return None
    try:
        content = read_volume_file(workspace, token, _join(base_path, rel))
    except RuntimeError as exc:
        print_warning(f"Skipped instruction file: {exc}")
        return None
    backup = _instructions_backup_path()
    backup_existing_file(CLAUDE_INSTRUCTIONS_PATH, backup)
    CLAUDE_INSTRUCTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_INSTRUCTIONS_PATH.write_text(content, encoding="utf-8")
    print_success(f"Wrote instructions to {CLAUDE_INSTRUCTIONS_PATH}")
    return str(CLAUDE_INSTRUCTIONS_PATH)


def _instructions_backup_path() -> Path:
    from ucode.config_io import APP_DIR

    return APP_DIR / "claude-CLAUDE.md.backup"


def apply_template(workspace: str, token: str, base_path: str, manifest: TemplateManifest) -> dict:
    """Apply a composed manifest to the local machine.

    Registers MCP services (reusing the existing ``configure mcp --services``
    backbone), copies skills, and writes the instruction file. Returns a
    tracking dict persisted into state so ``ucode revert`` can undo the
    net-new writes:

        {"template": <name>, "skills": [<dest dir>, ...],
         "instructions": [<path>, ...]}

    MCP entries are already tracked in ``state["mcp_servers"]`` by
    ``configure_mcp_command`` and reverted by the existing MCP revert path, so
    they are not duplicated here. Permissions/hooks are threaded through the
    agent overlay separately (Phase 3), not here."""
    if manifest.mcp_services:
        # Imported lazily: ucode.mcp imports ucode.agents, and importing it at
        # module load would widen this module's import graph unnecessarily.
        from ucode.mcp import configure_mcp_command

        print_note(f"Registering {len(manifest.mcp_services)} MCP service(s) from template...")
        try:
            configure_mcp_command(services=set(manifest.mcp_services))
        except RuntimeError as exc:
            # Soft-fail: a service the token can't see, or a schema mismatch,
            # shouldn't abort skills/instructions. UC ACLs are the boundary.
            print_warning(f"Some MCP services could not be registered: {exc}")

    skill_dirs = apply_skills(workspace, token, base_path, manifest)
    instruction_path = apply_instructions(workspace, token, base_path, manifest)

    return {
        "template": manifest.name,
        "skills": skill_dirs,
        "instructions": [instruction_path] if instruction_path else [],
    }


def revert_template(tracking: dict) -> None:
    """Undo the net-new writes recorded by :func:`apply_template`.

    Removes ucode-installed skill dirs and restores the instruction-file backup
    (or deletes the file if ucode created it with no prior version)."""
    from ucode.config_io import restore_file

    for skill_dir in tracking.get("skills") or []:
        path = Path(skill_dir)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    if tracking.get("instructions"):
        restore_file(CLAUDE_INSTRUCTIONS_PATH, _instructions_backup_path(), managed=True)
