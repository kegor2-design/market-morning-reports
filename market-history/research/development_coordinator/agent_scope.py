"""Operator approval and file validation for the local Agent development bridge."""

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

APPROVAL = "agent-development-scope.json"
SOURCE = re.compile(r"market-history/research/universal_agent/(?:tests/)?[A-Za-z_][A-Za-z_0-9]*\.py")
SELF_DEVELOPMENT_APPROVAL = "coordinator-self-development-scope.json"
COORDINATOR_DIRECTORY = "market-history/research/development_coordinator/"
SELF_DEVELOPMENT_FILES = frozenset(COORDINATOR_DIRECTORY + name for name in (
    "agent_scope.py", "coordinator.py", "feedback_loop.py", "test_coordinator.py",
    "test_feedback_loop.py", "README.md",
))
COORDINATOR_TEST_INPUT = re.compile(
    re.escape(COORDINATOR_DIRECTORY) + r"[A-Za-z_][A-Za-z_0-9]*\.py"
)


def git_bytes(root, *args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", root, *args], timeout=30)


def read_private_json(path):
    # Open once, without following links or waiting on a FIFO.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as f:
        meta = os.fstat(f.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid()
                or meta.st_nlink != 1 or meta.st_mode & 0o077):
            raise ValueError("Use a private, operator-owned regular scope file (mode 0600).")
        return json.load(f, object_pairs_hook=unique_object)


def unique_object(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("Approval contains a duplicate field.")
    return value


def read_scope(admin, issue_url, branch, base):
    scope = read_private_json(admin / APPROVAL)
    binding = {"issue_url": issue_url, "branch": branch, "base": base}
    if not isinstance(scope, dict) or scope.keys() != {*binding, "allowed_files"}:
        raise ValueError("Invalid operator scope fields.")
    if any(scope[k] != v for k, v in binding.items()):
        raise ValueError("Operator scope does not match the Issue, branch and pinned base.")
    paths = scope["allowed_files"]
    if (not isinstance(paths, list) or not paths
            or not all(isinstance(p, str) and SOURCE.fullmatch(p) for p in paths)
            or len(set(paths)) != len(paths)):
        raise ValueError("Approve distinct, exact Agent Python source paths.")
    return sorted(paths)


def read_self_development_scope(admin, issue_url, branch, base):
    scope = read_private_json(admin / SELF_DEVELOPMENT_APPROVAL)
    binding = {"issue_url": issue_url, "branch": branch, "base": base}
    if not isinstance(scope, dict) or scope.keys() != {*binding, "allowed_files"}:
        raise ValueError("Invalid Coordinator self-development approval fields.")
    if any(scope[key] != value for key, value in binding.items()):
        raise ValueError("Coordinator self-development approval does not match the Issue, branch and pinned base.")
    paths = scope["allowed_files"]
    if (not isinstance(paths, list) or not paths
            or not all(isinstance(name, str) and name in SELF_DEVELOPMENT_FILES for name in paths)
            or len(set(paths)) != len(paths)):
        raise ValueError("Approve distinct, exact Coordinator self-development paths.")
    return sorted(paths)


def read_approved_scope(admin, issue_url, branch, base, profile="agent"):
    if profile == "agent":
        return read_scope(admin, issue_url, branch, base)
    if profile == "coordinator-self-development":
        return read_self_development_scope(admin, issue_url, branch, base)
    raise ValueError("Unknown approval profile.")


def regular_file(root, name):
    path = root / name
    for parent in reversed(Path(name).parents):
        if not stat.S_ISDIR((root / parent).lstat().st_mode):
            raise ValueError(f"Non-directory or symlink in file path: {name!r}")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"Expected a single-link regular file: {name!r}")
    return info


def inspect_index(root):
    # Include ignored files. Do not open them. Git's ordinary porcelain omits them.
    others = git_bytes(root, "ls-files", "--others", "-z").split(b"\0")[:-1]
    if others:
        raise ValueError(f"Untracked or ignored path: {os.fsdecode(others[0])!r}")
    for item in git_bytes(root, "ls-files", "-v", "--stage", "-z").split(b"\0")[:-1]:
        if not item.startswith((b"H 100644 ", b"H 100755 ", b"H 120000 ")):
            raise ValueError("Require a full index without hidden entries or submodules.")


def source_modes(root, paths, base):
    modes = {}
    for name in paths:
        entry = git_bytes(root, "ls-tree", "-z", base, "--", name)
        meta, _, filename = entry.partition(b"\t")
        fields = meta.split()
        if (filename != os.fsencode(name) + b"\0" or len(fields) != 3
                or fields[0] not in (b"100644", b"100755") or fields[1] != b"blob"):
            raise ValueError(f"Approve only existing tracked regular source files: {name!r}")
        info = regular_file(root, name)
        if (info.st_mode & 0o7000 or bool(info.st_mode & stat.S_IXUSR) != (fields[0] == b"100755")):
            raise ValueError(f"Source mode differs from approval: {name!r}")
        if git_bytes(root, "hash-object", "--no-filters", "--", name).strip() != fields[2]:
            raise ValueError(f"Source bytes differ from the approved Git blob: {name!r}")
        modes[name] = stat.S_IMODE(info.st_mode)
    return modes


def capture_workspace(work, modes, directory_modes, verified):
    """Read each approved result once through a non-following directory descriptor."""
    seen = set()

    def raise_walk_error(error):
        raise error

    for directory, dirs, files, fd in os.fwalk(work, onerror=raise_walk_error):
        relative = Path(directory).relative_to(work)
        if stat.S_IMODE(os.fstat(fd).st_mode) != directory_modes[relative]:
            raise ValueError(f"Unexpected dispatch directory mode: {relative.as_posix()!r}")
        for child in dirs:
            name = (relative / child).as_posix()
            if (relative / child not in directory_modes
                    or not stat.S_ISDIR(os.stat(child, dir_fd=fd, follow_symlinks=False).st_mode)):
                raise ValueError(f"Unexpected dispatch directory or symlink: {name!r}")
        for child in files:
            name = (relative / child).as_posix()
            if name not in modes:
                raise ValueError(f"Unexpected dispatch file: {name!r}")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(child, flags, dir_fd=fd), "rb") as source:
                before = os.fstat(source.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or stat.S_IMODE(before.st_mode) != modes[name]):
                    raise ValueError(f"Unexpected dispatch file type, links or mode: {name!r}")
                target = verified / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                if os.fstat(source.fileno()).st_ctime_ns != before.st_ctime_ns:
                    raise ValueError(f"Dispatch file changed during inspection: {name!r}")
            seen.add(name)
    if missing := modes.keys() - seen:
        raise ValueError(f"Approved source removed or renamed: {sorted(missing)!r}")


def apply_edits(root, original, work, paths):
    """Build one textual patch. Git rejects an inapplicable patch as a unit."""
    patches = []
    changed = []
    for name in paths:
        result = subprocess.run(["diff", "-u", "--label", "a/" + name, "--label", "b/" + name,
                                 "--", original / name, work / name], stdout=subprocess.PIPE,
                                timeout=30, check=False)
        if result.returncode == 1 and result.stdout.startswith(b"--- "):
            patches.append(result.stdout)
            changed.append(name)
        elif result.returncode != 0:
            raise ValueError(f"Could not produce a source patch for {name!r}.")
    if patches:
        subprocess.run(["git", "-C", root, "apply", "--whitespace=nowarn", "-"],
                       input=b"".join(patches), check=True, timeout=30)
    return changed


def changed_paths(root, *diff_args):
    names = git_bytes(root, "diff", "--no-renames", "--name-only", "-z", *diff_args, "--")
    return sorted(os.fsdecode(p) for p in names.split(b"\0")[:-1])
