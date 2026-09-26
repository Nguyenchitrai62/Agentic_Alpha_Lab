"""Round 75 worker A-EVIDENCE: build + verify evidence_audit.json.

Read-only on existing artifacts (never modifies them). New output ONLY under
artifacts/research/opencode_r75_practical/evidence/.

Usage:
  .venv/Scripts/python.exe scripts/opencode_r75_evidence.py --build
  .venv/Scripts/python.exe scripts/opencode_r75_evidence.py --check
"""
import argparse
import hashlib
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "configs", "opencode_r75_evidence.json")
OUT_DIR = os.path.join(REPO, "artifacts", "research", "opencode_r75_practical", "evidence")
OUT_FILE = os.path.join(OUT_DIR, "evidence_audit.json")
LEDGER = os.path.join(REPO, "configs", "opencode_hypothesis_ledger.json")

DATE_RE = re.compile(r"20\d\d-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d)?[^\"\s]*)?")
MAX_HASH_BYTES = 50 * 1024 * 1024  # skip hashing files larger than this


def sha256_of(path):
    h = hashlib.sha256()
    size = os.path.getsize(path)
    if size > MAX_HASH_BYTES:
        return {"sha256": "SKIPPED_TOO_LARGE", "bytes": size}
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "bytes": size}


def mtime_iso(path):
    try:
        import datetime
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
    except OSError:
        return "UNKNOWN"


def extract_dates(obj, cap=25):
    try:
        s = json.dumps(obj)
    except (TypeError, ValueError):
        return []
    seen = []
    for m in DATE_RE.findall(s):
        if m not in seen:
            seen.append(m)
        if len(seen) >= cap:
            break
    return seen


def load_json_safely(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def audit_dir(abs_dir, key_files):
    row = {"artifact_dir": os.path.relpath(abs_dir, REPO).replace(os.sep, "/")}
    if not os.path.isdir(abs_dir):
        row["status"] = "MISSING_DIR"
        row["files"] = []
        return row
    row["status"] = "PRESENT"
    row["dir_mtime"] = mtime_iso(abs_dir)
    files = []
    for rel in key_files:
        ap = os.path.join(abs_dir, rel.replace("/", os.sep))
        entry = {"path": row["artifact_dir"] + "/" + rel}
        if os.path.isfile(ap):
            entry.update(sha256_of(ap))
            entry["mtime"] = mtime_iso(ap)
        else:
            entry["status"] = "MISSING"
            entry["mtime"] = "UNKNOWN"
        files.append(entry)
    # also record full listing (names only) for traceability
    try:
        names = sorted(os.listdir(abs_dir))
    except OSError:
        names = []
    row["files"] = files
    row["all_entries"] = names
    # summary.json mtime = first metric-exposure proxy
    summ = os.path.join(abs_dir, "summary.json")
    row["first_metric_exposure_time"] = mtime_iso(summ) if os.path.isfile(summ) else "UNKNOWN"
    # config/plan mtime = candidate registration proxy
    reg = "UNKNOWN"
    for cand in ("config.json", "plan.json"):
        cp = os.path.join(abs_dir, cand)
        if os.path.isfile(cp):
            reg = mtime_iso(cp)
            row["registration_proxy_file"] = row["artifact_dir"] + "/" + cand
            break
    row["candidate_registration_time"] = reg
    # date strings found in config/plan/summary
    dates = []
    for cand in ("plan.json", "config.json", "summary.json"):
        cp = os.path.join(abs_dir, cand)
        data = load_json_safely(cp)
        if data is not None:
            for d in extract_dates(data):
                if d not in dates:
                    dates.append(d)
    row["model_fit_calibration_dates"] = dates if dates else "UNKNOWN"
    return row


def build():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    ledger_mtime = mtime_iso(LEDGER) if os.path.isfile(LEDGER) else "UNKNOWN"
    families = []
    for fam in manifest["claim_families"]:
        frow = {
            "family": fam["family"],
            "test_range": fam.get("known_test_range", "UNKNOWN"),
            "selection_dependencies": fam.get("selection_dependencies", "UNKNOWN"),
        }
        main = audit_dir(os.path.join(REPO, fam["artifact_dir"].replace("/", os.sep)),
                         fam.get("key_files", []))
        frow["primary"] = main
        sibs = []
        for s in fam.get("sibling_dirs", []):
            # hash summary.json + config.json where present
            sibs.append(audit_dir(os.path.join(REPO, s.replace("/", os.sep)),
                                  ["config.json", "summary.json", "SHA256SUMS.txt"]))
        frow["siblings"] = sibs
        # Uncertain exposure is NEVER clean-by-default: registration/exposure
        # proxies are file mtimes, which prove existence-not-independence.
        frow["exposure_note"] = (
            "Registration/exposure times are file-mtime proxies (existence only). "
            "A later date than model training does NOT prove prospective deployment "
            "or selection independence. Uncertain exposure is marked UNKNOWN, never clean-by-default."
        )
        families.append(frow)
    audit = {
        "round": manifest.get("round"),
        "ledger_mtime": ledger_mtime,
        "generated_by": "scripts/opencode_r75_evidence.py --build (read-only on artifacts)",
        "claim_families": families,
        "dataset_classification": [
            {"dataset": "2023-2026 development interval (opened, inspected)",
             "class": "development",
             "proof": "forward protocol in_sample_interval_note + ledger rounds 1-26 tuning history on it"},
            {"dataset": "sealed forward window 2026-03-23/2026-09-08 (7+ forward OOS evals observed)",
             "class": "historical-OOS-already-observed",
             "proof": "v135/v138/v152/v154/v159 summaries report metrics exactly once; returns influenced candidate choice per assignment finding 1"},
            {"dataset": "genuinely-untouched recent holdout",
             "class": "NONE_EXISTS",
             "proof": "no demonstrated untouched interval; sealed window stays sealed, no new evals run this round"},
            {"dataset": "prospective shadow (future candles, paper/shadow pipeline)",
             "class": "prospective-shadow",
             "proof": "collection contract only (tracks B/C); no observations yet this round"},
        ],
        "sealed_window_rule": (
            "NO untouched recent interval exists except the sealed forward window, which stays sealed: "
            "do NOT run new evals on it; do NOT recrawl opened months as a new test."
        ),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print("wrote " + os.path.relpath(OUT_FILE, REPO))
    return 0


REQUIRED_TOP = ["round", "claim_families", "dataset_classification", "sealed_window_rule"]


def check():
    errors = []
    if not os.path.isfile(OUT_FILE):
        print("MISSING " + os.path.relpath(OUT_FILE, REPO))
        return 1
    with open(OUT_FILE, "r", encoding="utf-8") as f:
        audit = json.load(f)
    for k in REQUIRED_TOP:
        if k not in audit:
            errors.append("missing top-level key: " + k)
    if not isinstance(audit.get("claim_families"), list) or not audit["claim_families"]:
        errors.append("claim_families must be a non-empty list")
    n_unknown = 0
    for fam in audit.get("claim_families", []):
        for k in ("family", "primary", "selection_dependencies", "exposure_note"):
            if k not in fam:
                errors.append("family %r missing %s" % (fam.get("family"), k))
        prim = fam.get("primary", {})
        if prim.get("candidate_registration_time") == "UNKNOWN":
            n_unknown += 1
        if prim.get("first_metric_exposure_time") == "UNKNOWN":
            n_unknown += 1
        if prim.get("model_fit_calibration_dates") == "UNKNOWN":
            n_unknown += 1
        for fe in prim.get("files", []):
            if fe.get("sha256") in (None, "MISSING"):
                continue
            if "path" not in fe or "mtime" not in fe:
                errors.append("file entry malformed in %r" % fam.get("family"))
            ap = os.path.join(REPO, fe["path"].replace("/", os.sep))
            if os.path.isfile(ap) and fe.get("sha256") not in ("SKIPPED_TOO_LARGE",):
                actual = sha256_of(ap)["sha256"]
                if actual != fe["sha256"]:
                    errors.append("hash mismatch: " + fe["path"])
            elif not os.path.isfile(ap) and "status" not in fe:
                errors.append("file vanished since audit: " + fe["path"])
    if n_unknown == 0:
        errors.append("expected some UNKNOWN markings for uncertain exposure; none found")
    if errors:
        print("CHECK FAILED:")
        for e in errors:
            print(" - " + e)
        return 1
    print("CHECK OK: %d families, UNKNOWN-proxy count=%d" % (len(audit["claim_families"]), n_unknown))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    return build()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
