#!/usr/bin/env python3
"""DONNA memory contract check for staged changes (git pre-commit hook).

Rules: DONNA-MEMORY.md (vault root). Allowed values: resources/donna/contract.yaml.
Managed from ai_stack_infra (stacks/agents/cornelius/vault); do not edit in the vault.

Checks only what is staged (`git diff --cached`):
  * new notes under Brain/ (outside exempt paths) carry the full DONNA frontmatter;
  * notes that already carry donna_id keep it; curated notes are frozen except for a few keys;
  * originated / endorsed provenance and the move to curated need donna_approved_via;
  * curated DONNA notes are not deleted (supersede them instead);
  * no secrets in any staged file.
Exit code 1 with a list of problems if anything fails.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

REPO = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                           text=True, check=True).stdout.strip())
CONTRACT = yaml.safe_load((REPO / "resources/donna/contract.yaml").read_text(encoding="utf-8"))

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic key/token"),
    (re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{32,}"), "OpenAI-style key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"), "GitHub token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"tskey-[A-Za-z0-9-]{10,}"), "Tailscale key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]

errors: list[str] = []


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                          cwd=REPO).stdout


def blob(rev_path: str) -> str | None:
    r = subprocess.run(["git", "show", rev_path], capture_output=True, cwd=REPO)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def split_note(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter dict or None, body)."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        return {"__yaml_error__": str(exc)}, text[end + 4:]
    if not isinstance(fm, dict):
        fm = {"__yaml_error__": "frontmatter is not a mapping"}
    return fm, text[end + 4:].lstrip("\n")


def is_note(path: str) -> bool:
    return path.startswith("Brain/") and path.endswith(".md")


def exempt(path: str) -> bool:
    return any(path.startswith(p) for p in CONTRACT["exempt_paths"])


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def valid_date(value) -> bool:
    if isinstance(value, (dt.date, dt.datetime)):
        return True
    try:
        dt.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def valid_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


TASK_RE = re.compile(CONTRACT["task_pattern"])


def check_contract(path: str, fm: dict) -> None:
    """Full contract for a DONNA record."""
    def err(msg: str) -> None:
        errors.append(f"{path}: {msg}")

    if "__yaml_error__" in fm:
        err(f"frontmatter is not valid YAML ({fm['__yaml_error__']})")
        return
    if not valid_uuid(fm.get("donna_id")):
        err("donna_id missing or not a UUID (cat /proc/sys/kernel/random/uuid)")
    ktype = fm.get("donna_type")
    if ktype not in CONTRACT["knowledge_types"]:
        err(f"donna_type must be one of {CONTRACT['knowledge_types']}")
    kind = fm.get("donna_kind")
    if kind is not None and kind not in CONTRACT["kinds"].get(ktype, []):
        err(f"donna_kind '{kind}' is not allowed for {ktype} ({CONTRACT['kinds'].get(ktype, [])})")
    state = fm.get("donna_state")
    if state not in CONTRACT["states"]:
        err(f"donna_state must be one of {CONTRACT['states']}")
    prov = fm.get("provenance")
    if prov not in CONTRACT["provenance"]:
        err(f"provenance must be one of {CONTRACT['provenance']}")
    if fm.get("confidence") not in CONTRACT["confidence"]:
        err(f"confidence must be one of {CONTRACT['confidence']}")
    scopes = as_list(fm.get("donna_scopes"))
    if not scopes:
        err("donna_scopes must list at least one scope")
    bad = [s for s in scopes if s not in CONTRACT["scopes"]]
    if bad:
        err(f"unknown donna_scopes {bad}; allowed {CONTRACT['scopes']}")
    sources = as_list(fm.get("donna_sources"))
    if prov in ("encountered", "reference", "ai-inferred") and not sources:
        err(f"donna_sources must not be empty for provenance {prov}")
    task = fm.get("donna_task")
    if not (isinstance(task, str) and TASK_RE.match(task)):
        err("donna_task must be the Paperclip issue id, e.g. RBV-12")
    approved = fm.get("donna_approved_via")
    needs_approval = prov in CONTRACT["provenance_needs_approval"] or state == "curated"
    if needs_approval and not (isinstance(approved, str) and TASK_RE.match(approved)):
        err(f"donna_approved_via (Paperclip issue id) is required for provenance {prov} / state {state}")
    if approved is not None and not (isinstance(approved, str) and TASK_RE.match(approved)):
        err("donna_approved_via must be a Paperclip issue id")
    vf, vt = fm.get("donna_valid_from"), fm.get("donna_valid_to")
    if vf is not None and not valid_date(vf):
        err("donna_valid_from must be a date (YYYY-MM-DD)")
    if vt is not None and not valid_date(vt):
        err("donna_valid_to must be a date (YYYY-MM-DD)")
    if vf is not None and vt is not None and valid_date(vf) and valid_date(vt) \
            and dt.date.fromisoformat(str(vt)[:10]) < dt.date.fromisoformat(str(vf)[:10]):
        err("donna_valid_to is before donna_valid_from")
    for key in ("donna_supersedes", "donna_contradicts", "donna_superseded_by", "donna_contradicted_by"):
        bad_ids = [v for v in as_list(fm.get(key)) if not valid_uuid(v)]
        if bad_ids:
            err(f"{key} must list donna_id values (UUIDs), got {bad_ids}")


def check_change(path: str, old_fm: dict | None, old_body: str, new_fm: dict, new_body: str) -> None:
    """Rules for a modified note."""
    def err(msg: str) -> None:
        errors.append(f"{path}: {msg}")

    old_fm = old_fm or {}
    if "donna_id" in old_fm:
        if new_fm.get("donna_id") != old_fm["donna_id"]:
            err("donna_id must never change")
        check_contract(path, new_fm)
        if old_fm.get("donna_state") == "curated":
            if new_body.strip() != old_body.strip():
                err("curated note text is frozen; write a new note with donna_supersedes instead")
            mutable = set(CONTRACT["curated_mutable_keys"])
            for key in set(old_fm) | set(new_fm):
                if key in mutable:
                    continue
                if old_fm.get(key) != new_fm.get(key):
                    err(f"'{key}' of a curated note is frozen (only {sorted(mutable)} may change)")
        return
    # Legacy (seed) note or a note getting the contract for the first time.
    if any(k.startswith("donna_") for k in new_fm):
        check_contract(path, new_fm)
    elif new_fm.get("provenance") in CONTRACT["provenance_needs_approval"] \
            and old_fm.get("provenance") != new_fm.get("provenance"):
        err("provenance originated/endorsed needs the DONNA frontmatter with donna_approved_via")


def main() -> int:
    changes = git("diff", "--cached", "--name-status", "-M", "--diff-filter=ACDMR").splitlines()
    added_ids: dict[str, str] = {}
    staged: list[tuple[str, str, str | None]] = []  # (status, path, old_path)
    for line in changes:
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            staged.append(("R", parts[2], parts[1]))
        else:
            staged.append((status, parts[1], None))

    for status, path, old_path in staged:
        if status == "D":
            continue
        text = blob(f":{path}") or ""
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path}: looks like it contains a secret ({label}); remove it")
        if not is_note(path):
            continue
        fm, body = split_note(text)
        fm = fm or {}
        if valid_uuid(fm.get("donna_id")):
            added_ids[str(fm["donna_id"])] = path
        if exempt(path):
            continue
        if status in ("A", "C"):
            check_contract(path, fm)
        else:  # M or R
            old_text = blob(f"HEAD:{old_path or path}") or ""
            old_fm, old_body = split_note(old_text)
            check_change(path, old_fm, old_body, fm, body)

    for status, path, _ in staged:
        if status != "D" or not is_note(path) or exempt(path):
            continue
        old_fm, _ = split_note(blob(f"HEAD:{path}") or "")
        old_fm = old_fm or {}
        if old_fm.get("donna_state") == "curated" and str(old_fm.get("donna_id")) not in added_ids:
            errors.append(f"{path}: curated notes are not deleted; supersede them with a new note")

    if errors:
        print("DONNA memory contract: commit rejected (rules: DONNA-MEMORY.md)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
