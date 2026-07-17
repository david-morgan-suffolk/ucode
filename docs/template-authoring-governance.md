# Discussion: Governing who can author agent templates

**Status:** Open question for group decision
**Audience:** Platform / data governance group
**Decision needed:** Who is allowed to publish role/project templates, and how is that access managed?

---

## Background

`ucode` can distribute **templates** — curated bundles of agent resources (MCP
tool sets, coding-assistant skills, instruction files, permission policies, and
hooks) — from a central store. When someone configures their agent, ucode fetches
the template(s) that apply to them (by explicit choice or by group membership),
composes them, and applies them locally.

The store is a shared, versioned location:

- **Read access** is broad (all staff), so anyone can *consume* templates.
- Access to the underlying tools/models a template references is still enforced
  separately, so a template naming a resource you can't reach simply skips it.

That model is settled. The open question is about the **write side**.

---

## Why authoring needs its own control

A template is not just static config. It can carry:

- **Permission policies** — what the agent is allowed and denied to do.
- **Hooks** — commands that run automatically at defined points in an agent
  session.

Because templates can be **auto-selected by group membership**, a template that
someone publishes may be picked up and applied by many staff **without each
person opting in per template**. That makes the publish step a
**supply-chain-style trust boundary**: whoever can write to the store can, in
effect, change what runs on many machines.

So "who can read templates" and "who can publish templates" are two different
questions with two different risk profiles. Read is low-risk and broad. **Publish
should be restricted and deliberately governed.**

---

## What we found while setting this up

We hit a concrete platform constraint worth knowing before deciding:

- Fine-grained data-access grants (the thing that would gate "who can write to
  the store") are resolved at the **account/identity-provider level**, not at the
  level of a single workspace.
- A group created **locally inside one workspace** is **not visible** to that
  grant system, so it **cannot** be used to hold a write permission on the store.
- Therefore an "authoring group" has to be an **account-/directory-level group**,
  created by an identity/account administrator — not something provisioned ad hoc
  inside a single workspace.

**Implication:** standing up the authoring control is partly an
**identity-administration task**, not purely a ucode/data task. It needs an
account admin in the loop.

---

## Options for who holds write access

| Option | What it is | Pros | Cons |
|---|---|---|---|
| **A. Dedicated authoring group** (account-level) | A new directory group, e.g. "template authors"; write access granted to the group; membership managed centrally | Clear, auditable, easy to add/remove people; membership is the control | Requires an account admin to create + maintain; another group to govern |
| **B. Reuse an existing group** | Point write access at a group that already means "platform/governance owners" | No new group; leans on existing governance | Only clean if such a group already maps well to "allowed to publish"; risks over-granting |
| **C. Named individuals** | Grant write directly to specific people | Works immediately; no new group needed | Doesn't scale; no single place to see/manage who can publish; easy to drift |

A common pattern is **A as the target end-state**, with **C as a short-term
bridge** if we need to publish before the group exists.

---

## Questions for the group

1. **Should authoring be group-governed (A/B) or is named-individual (C)
   acceptable, at least to start?**
2. **If a dedicated group (A): who owns its membership**, and what's the process
   to request being added / removed?
3. **Who are the initial authors?** (Names or an existing group.)
4. **Do we require review before publish** (e.g. templates land via pull request /
   change review) in addition to the write grant — i.e. is write access alone
   enough, or is a second control wanted given hooks/permissions run on others'
   machines?
5. **Who is the account/identity admin** that will create the authoring group and
   apply the write grant?
6. **Environments:** do we govern authoring the same way in test vs. production,
   or is test intentionally looser?

---

## Suggested default (for the group to accept or change)

- **Broad read, restricted write.** Keep read open to all staff; restrict publish.
- **Target: a dedicated account-level authoring group** (Option A), created by an
  account admin, with membership as the primary control.
- **Add change-review on top** (templates published via reviewed change, not
  direct edits) because templates can carry hooks and permission policy — write
  access alone is a blunt instrument for something that executes on many machines.
- **Bridge if needed:** grant a couple of named owners write access temporarily
  (Option C) so work isn't blocked, then migrate to the group once it exists.

---

## Decision log

| Date | Decision | Owner |
|---|---|---|
| _tbd_ | | |
