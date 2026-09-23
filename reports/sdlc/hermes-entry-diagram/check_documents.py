"""Offline content checks for the documentation candidate, not runtime trading tests."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3]
files = ["README.md", "docs/trading-operations.md", "docs/architecture.md"]
checked = 0
for name in files:
    source = root / name
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", source.read_text()):
        if re.match(r"[a-z]+://", target):
            continue
        relative, _, fragment = target.partition("#")
        dest = (source.parent / relative) if relative else source
        assert dest.is_file(), (name, target)
        if fragment and dest.suffix == ".md":
            headings = re.findall(r"^#+ (.+)$", dest.read_text(), re.M)
            anchors = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-") for h in headings]
            assert fragment in anchors, (name, target)
        checked += 1
print(f"PASS: {checked} local documentation links/anchors")

for args, required in [
    (["order", "prepare"], ["--input"]),
    (["order", "preview"], ["--input"]),
    (["order", "submit"], ["--input", "--live"]),
    (["order", "status"], ["--id"]),
    (["supervisor", "run"], ["--venue", "--live", "--once"]),
    (["signal", "execute"], ["--id", "--input", "--manual", "--grant", "--live"]),
]:
    result = subprocess.run(["python3", "-m", "kis_hl.cli", *args, "--help"], cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert all(flag in result.stdout for flag in required), args
    print("PASS: CLI help", " ".join(args))

candidate = json.loads((root / "reports/sdlc/hermes-entry-diagram/candidate.json").read_text())
for name, digest in candidate["files"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
print("PASS: exact documentation candidate hashes")
changes = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=root, text=True).splitlines()
assert set(changes) <= set(files), changes
untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
assert all(p.startswith(("docs/architecture/hermes-entry.", "reports/sdlc/hermes-entry-diagram/", ".planning/")) for p in untracked), untracked
print("PASS: tracked and new file scope contains no runtime edits")
