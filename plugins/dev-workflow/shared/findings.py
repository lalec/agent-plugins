"""Turn one scanner's output into findings scan.py can compare, rate and hold on.

Readers: SARIF 2.1.0 (most tools), osv-scanner JSON (it carries package + version, the
key /audit already writes), ZAP baseline JSON. A finding never carries a snippet: the
fingerprint hashes the flagged line, and the secrets slot hashes the commit instead, so
no secret value and no author data ever leaves the tool's own output file.
"""
import hashlib
import json
import re
from pathlib import Path

RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unrated": 0}
LEVEL = {"error": "high", "warning": "medium", "note": "low"}
CWE_RE = re.compile(r"CWE-\d+")


def score_to_severity(score) -> str:
    """GitHub's security-severity ranges — a convention, not part of SARIF."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "unrated"
    return "critical" if s >= 9 else "high" if s >= 7 else "medium" if s >= 4 else "low" if s > 0 else "unrated"


def _rel(uri: str, root: Path) -> str:
    p = re.sub(r"^file://", "", uri or "")
    if p.startswith(str(root)):
        return str(Path(p).relative_to(root))
    return (p[2:] if p.startswith("./") else p) or "-"


def _line_text(root: Path, file: str, line: int) -> str:
    try:
        return (root / file).read_text(errors="replace").splitlines()[line - 1].strip()
    except (OSError, IndexError):
        return ""


def _finding(slot, rule, file, line, severity, cwe="", basis="", dep=None):
    return {"slot": slot, "rule": rule, "file": file, "line": line, "severity": severity,
            "cwe": cwe, "basis": basis, "dep": dep}


def read_sarif(data: dict, slot: str, root: Path) -> list[dict]:
    out = []
    for run in data.get("runs") or []:
        rules = {r.get("id"): r for r in (run.get("tool", {}).get("driver", {}).get("rules") or [])}
        for r in run.get("results") or []:
            rule = rules.get(r.get("ruleId"), {})
            loc = ((r.get("locations") or [{}])[0]).get("physicalLocation", {})
            file = _rel(loc.get("artifactLocation", {}).get("uri", ""), root)
            line = int(loc.get("region", {}).get("startLine") or 0)
            # A suppression comment counts only in the workflow's own tools under .claude/, which
            # ship nowhere and carry their reason beside it. In product code it is not a decision:
            # an agent could write one to quiet the gate, so the finding still needs a vex.yaml statement.
            if r.get("suppressions") and file.startswith(".claude/"):
                continue
            sev = score_to_severity((r.get("properties") or {}).get("security-severity")
                                    or (rule.get("properties") or {}).get("security-severity"))
            if sev == "unrated":
                level = r.get("level") or (rule.get("defaultConfiguration") or {}).get("level")
                sev = LEVEL.get(level, "unrated")
            tags = " ".join((rule.get("properties") or {}).get("tags") or [])
            cwe = (CWE_RE.findall(tags) or [""])[0]
            # Secrets: a commit is immutable, so commit + file + line identifies the leak
            # without reading it. Everything else: the flagged line's text, so a line that
            # moves keeps its identity.
            commit = (r.get("partialFingerprints") or {}).get("commitSha", "")
            basis = f"{commit}:{line}" if commit else _line_text(root, file, line)
            out.append(_finding(slot, r.get("ruleId") or "-", file, line, sev, cwe, basis))
    return out


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def _fix(vuln: dict, name: str, ver: str) -> str | None:
    """The lowest version that fixes this advisory for `name`, above the installed one; None when
    no fixed version is published."""
    fixed = [e["fixed"] for a in vuln.get("affected") or []
             if (a.get("package") or {}).get("name", "").lower() == name.lower()
             for r in a.get("ranges") or [] if r.get("type") in ("ECOSYSTEM", "SEMVER")
             for e in r.get("events") or [] if "fixed" in e]  # a GIT range's fix is a commit, not a version
    above = [f for f in fixed if _vkey(f) > _vkey(ver)]
    return min(above, key=_vkey) if above else None


def read_osv(data: dict, slot: str, root: Path) -> list[dict]:
    out = []
    for res in data.get("results") or []:
        file = _rel(res.get("source", {}).get("path", ""), root)
        for pkg in res.get("packages") or []:
            name = pkg.get("package", {}).get("name", "")
            ver = pkg.get("package", {}).get("version", "")
            vulns = {v.get("id"): v for v in pkg.get("vulnerabilities") or []}
            # One finding per group: osv-scanner groups an advisory with its aliases
            # (GHSA, PYSEC, CVE), and one flaw must not need three decisions.
            groups = pkg.get("groups") or [{"ids": [i]} for i in vulns]
            for g in groups:
                ids = sorted(g.get("ids") or [], key=lambda i: (not i.startswith("GHSA"), i))
                if not ids:
                    continue
                db = json.dumps([vulns.get(i, {}).get("database_specific") or {} for i in ids])
                cwe = (CWE_RE.findall(db) or [""])[0]
                # The group's fix is the version that fixes every alias; any alias with none → no fix.
                fixes = [_fix(vulns[i], name, ver) for i in ids if i in vulns]
                fix = max(fixes, key=_vkey) if fixes and all(fixes) else None
                out.append(_finding(slot, ids[0], file, 0, score_to_severity(g.get("max_severity")),
                                    cwe, f"{name}@{ver}", {"id": ids[0], "package": name, "version": ver,
                                                           "aliases": ids, "fixed": fix}))
    return out


def read_zap(data: dict, slot: str, root: Path) -> list[dict]:
    out = []
    risk = {"3": "high", "2": "medium", "1": "low", "0": "low"}
    for site in data.get("site") or []:
        for a in site.get("alerts") or []:
            for inst in a.get("instances") or [{}]:
                url = inst.get("uri") or site.get("@name", "-")
                out.append(_finding(slot, str(a.get("pluginid", "-")), url, 0, risk.get(str(a.get("riskcode")), "unrated"),
                                    f"CWE-{a['cweid']}" if str(a.get("cweid", "")).isdigit() else "", inst.get("param", "")))
    return out


READERS = {"sarif": read_sarif, "osv-json": read_osv, "zap-json": read_zap}


def read(path: Path, fmt: str, slot: str, root: Path) -> list[dict]:
    """Raises on missing or unparseable output — the caller records the slot `errored`."""
    findings = READERS[fmt or "sarif"](json.loads(path.read_text()), slot, root)
    seen: dict[str, int] = {}
    for f in findings:
        if f["dep"]:
            f["key"] = f"{f['dep']['id']}@{f['dep']['package']}"
        else:
            # The nth identical line in a file is its own finding: a second copy of a
            # baselined line must surface, not hide behind the first one's hash.
            h = hashlib.sha256(f"{slot}|{f['rule']}|{f['file']}|{f['basis']}".encode()).hexdigest()[:12]
            seen[h] = seen.get(h, 0) + 1
            f["key"] = f"{slot}/{f['rule']}/{h}#{seen[h]}"
        del f["basis"]
    return findings
