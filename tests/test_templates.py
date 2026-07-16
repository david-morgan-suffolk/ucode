"""Tests for role/project template distribution."""

from __future__ import annotations

import json

import pytest

from ucode import databricks as db_mod
from ucode import templates as tmpl

WS = "https://example.databricks.com"
BASE = "/Volumes/business_functions/ucode/templates"


class TestGetCurrentUserGroups:
    def test_returns_display_names(self, monkeypatch):
        payload = {
            "userName": "user@example.com",
            "groups": [
                {"display": "data-engineers", "value": "1"},
                {"display": "all-staff", "value": "2"},
            ],
        }
        monkeypatch.setattr(db_mod, "_http_get_json", lambda url, token: (payload, None))
        assert db_mod.get_current_user_groups(WS, "tok") == ["data-engineers", "all-staff"]

    def test_empty_on_no_groups_key(self, monkeypatch):
        monkeypatch.setattr(db_mod, "_http_get_json", lambda url, token: ({"userName": "u"}, None))
        assert db_mod.get_current_user_groups(WS, "tok") == []

    def test_empty_on_failure(self, monkeypatch):
        monkeypatch.setattr(db_mod, "_http_get_json", lambda url, token: (None, "HTTP 403"))
        assert db_mod.get_current_user_groups(WS, "tok") == []

    def test_skips_malformed_entries(self, monkeypatch):
        payload = {
            "groups": [{"value": "no-display"}, "junk", {"display": "  "}, {"display": "ok"}]
        }
        monkeypatch.setattr(db_mod, "_http_get_json", lambda url, token: (payload, None))
        assert db_mod.get_current_user_groups(WS, "tok") == ["ok"]


class TestVolumeFilesApiPath:
    def test_strips_leading_slash_preserves_inner(self):
        assert (
            db_mod._volume_files_api_path("/Volumes/c/s/v/index.json") == "Volumes/c/s/v/index.json"
        )

    def test_encodes_spaces(self):
        assert "%20" in db_mod._volume_files_api_path("/Volumes/c/s/v/a b.json")


class TestManifestFromDict:
    def test_qualifies_relative_paths_with_template_dir(self):
        m = tmpl.TemplateManifest.from_dict(
            "data-engineer",
            {
                "mcp": {"services": ["system.ai.github"]},
                "skills": ["skills/sql-review"],
                "instructions": {"claude": "instructions/CLAUDE.md"},
            },
        )
        assert m.mcp_services == ["system.ai.github"]
        # Skills/instructions get prefixed with the template dir so composition
        # keeps them pointing at the right template under base_path.
        assert m.skills == ["data-engineer/skills/sql-review"]
        assert m.instructions == {"claude": "data-engineer/instructions/CLAUDE.md"}

    def test_tolerates_missing_and_wrong_types(self):
        m = tmpl.TemplateManifest.from_dict("x", {"skills": "notalist", "mcp": "nope"})
        assert m.skills == []
        assert m.mcp_services == []


class TestCompose:
    def _m(self, name, **kw):
        return tmpl.TemplateManifest(name=name, **kw)

    def test_unions_mcp_and_skills_dedup(self):
        a = self._m("shared", mcp_services=["system.ai.github"], skills=["shared/skills/x"])
        b = self._m(
            "de",
            mcp_services=["system.ai.github", "system.ai.dbt"],
            skills=["de/skills/y"],
        )
        out = tmpl.compose([a, b])
        assert out.mcp_services == ["system.ai.github", "system.ai.dbt"]
        assert out.skills == ["shared/skills/x", "de/skills/y"]

    def test_later_instructions_win_per_key(self):
        a = self._m("shared", instructions={"claude": "shared/i/A.md"})
        b = self._m("de", instructions={"claude": "de/i/B.md"})
        out = tmpl.compose([a, b])
        assert out.instructions == {"claude": "de/i/B.md"}

    def test_permissions_deny_union(self):
        a = self._m("shared", permissions={"deny": ["WebSearch"]})
        b = self._m("de", permissions={"deny": ["WebSearch", "Bash(rm*)"]})
        out = tmpl.compose([a, b])
        assert out.permissions["deny"] == ["WebSearch", "Bash(rm*)"]

    def test_empty_raises(self):
        with pytest.raises(RuntimeError):
            tmpl.compose([])


class TestLoadComposed:
    def test_extends_ordered_before_dependent(self, monkeypatch):
        store = {
            "shared": {"name": "shared", "mcp": {"services": ["system.ai.github"]}},
            "data-engineer": {
                "name": "data-engineer",
                "extends": ["shared"],
                "mcp": {"services": ["system.ai.dbt"]},
            },
        }

        def fake_fetch(workspace, token, base_path, name):
            return tmpl.TemplateManifest.from_dict(name, store[name])

        monkeypatch.setattr(tmpl, "fetch_template", fake_fetch)
        out = tmpl.load_composed(WS, "tok", BASE, ["data-engineer"])
        # shared merged first, so github precedes dbt.
        assert out.mcp_services == ["system.ai.github", "system.ai.dbt"]

    def test_cycle_does_not_infinite_loop(self, monkeypatch):
        store = {
            "a": {"name": "a", "extends": ["b"], "mcp": {"services": ["system.ai.a"]}},
            "b": {"name": "b", "extends": ["a"], "mcp": {"services": ["system.ai.b"]}},
        }
        monkeypatch.setattr(
            tmpl,
            "fetch_template",
            lambda w, t, b, name: tmpl.TemplateManifest.from_dict(name, store[name]),
        )
        out = tmpl.load_composed(WS, "tok", BASE, ["a"])
        assert set(out.mcp_services) == {"system.ai.a", "system.ai.b"}


class TestResolveTemplateNames:
    def test_explicit_wins_and_skips_scim(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("SCIM should not be consulted for explicit templates")

        monkeypatch.setattr(tmpl, "get_current_user_groups", boom)
        monkeypatch.setattr(tmpl, "fetch_index", boom)
        assert tmpl.resolve_template_names(WS, "tok", BASE, ["de", "de"]) == ["de"]

    def test_group_match(self, monkeypatch):
        index = {"groups": {"data-engineers": ["shared", "data-engineer"]}, "default": ["shared"]}
        monkeypatch.setattr(tmpl, "fetch_index", lambda w, t, b: index)
        monkeypatch.setattr(tmpl, "get_current_user_groups", lambda w, t: ["data-engineers"])
        assert tmpl.resolve_template_names(WS, "tok", BASE, None) == ["shared", "data-engineer"]

    def test_falls_back_to_default_when_no_group_match(self, monkeypatch):
        index = {"groups": {"data-engineers": ["data-engineer"]}, "default": ["shared"]}
        monkeypatch.setattr(tmpl, "fetch_index", lambda w, t, b: index)
        monkeypatch.setattr(tmpl, "get_current_user_groups", lambda w, t: ["some-other-group"])
        assert tmpl.resolve_template_names(WS, "tok", BASE, None) == ["shared"]

    def test_empty_when_no_default_no_match(self, monkeypatch):
        monkeypatch.setattr(tmpl, "fetch_index", lambda w, t, b: {"groups": {}})
        monkeypatch.setattr(tmpl, "get_current_user_groups", lambda w, t: [])
        assert tmpl.resolve_template_names(WS, "tok", BASE, None) == []


class TestFetchIndex:
    def test_parses_json(self, monkeypatch):
        monkeypatch.setattr(
            tmpl, "read_volume_file", lambda w, t, path: json.dumps({"default": ["shared"]})
        )
        assert tmpl.fetch_index(WS, "tok", BASE) == {"default": ["shared"]}

    def test_raises_on_bad_json(self, monkeypatch):
        monkeypatch.setattr(tmpl, "read_volume_file", lambda w, t, path: "{not json")
        with pytest.raises(RuntimeError):
            tmpl.fetch_index(WS, "tok", BASE)


class TestApplyAndRevert:
    """End-to-end apply -> revert of the net-new writers against a temp HOME.

    Guards the two bugs found during live e2e: (1) skills/instructions must land
    and revert cleanly, and (2) revert must remove the tracked skill dir even
    when a later flow no longer references it (strict-replacement contract)."""

    def _stub_volume(self, monkeypatch):
        vol = {
            "/V/de/skills/sql-review/SKILL.md": "skill body",
            "/V/de/instructions/CLAUDE.md": "role instructions",
        }
        monkeypatch.setattr(tmpl, "read_volume_file", lambda w, t, path: vol[path])
        monkeypatch.setattr(
            tmpl,
            "list_volume_dir",
            lambda w, t, path: (
                [
                    {
                        "name": "SKILL.md",
                        "path": "/V/de/skills/sql-review/SKILL.md",
                        "is_directory": False,
                    }
                ]
                if path == "/V/de/skills/sql-review"
                else []
            ),
        )

    def test_apply_then_revert_round_trips(self, monkeypatch, tmp_path):
        self._stub_volume(monkeypatch)
        monkeypatch.setattr(tmpl, "CLAUDE_SKILLS_DIR", tmp_path / ".claude" / "skills")
        monkeypatch.setattr(tmpl, "CLAUDE_INSTRUCTIONS_PATH", tmp_path / ".claude" / "CLAUDE.md")
        monkeypatch.setattr(tmpl, "_instructions_backup_path", lambda: tmp_path / "backup.md")
        m = tmpl.TemplateManifest(
            name="de",
            skills=["de/skills/sql-review"],
            instructions={"claude": "de/instructions/CLAUDE.md"},
        )
        skills = tmpl.apply_skills(WS, "tok", "/V", m)
        instr = tmpl.apply_instructions(WS, "tok", "/V", m)

        skill_file = tmp_path / ".claude" / "skills" / "sql-review" / "SKILL.md"
        instr_file = tmp_path / ".claude" / "CLAUDE.md"
        assert skill_file.read_text() == "skill body"
        assert instr_file.read_text() == "role instructions"

        tmpl.revert_template({"skills": skills, "instructions": instr})
        assert not (tmp_path / ".claude" / "skills" / "sql-review").exists()
        assert not instr_file.exists()  # ucode created it (no prior backup) -> removed

    def test_revert_removes_tracked_skill_dir(self, tmp_path):
        # A prior template's tracking must fully clean up its skill dir even when
        # nothing re-references it — the strict-replacement contract.
        skill_dir = tmp_path / "skills" / "sql-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("x")
        tmpl.revert_template({"skills": [str(skill_dir)], "instructions": []})
        assert not skill_dir.exists()
