#!/usr/bin/env sh
# Regenerate docs/third-party-licences.md from what is actually installed.
# Run after any dependency change. The obligation under MIT and ISC is to carry
# the notice, and a notice file that drifts from the lockfile does not carry it.
set -e
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json, pathlib
root = pathlib.Path("app/node_modules")
runtime = ["react", "react-dom", "lucide-react", "scheduler", "loose-envify", "js-tokens"]
build = ["vite", "@vitejs/plugin-react"]
out = ["# Third party licences", "",
       "Generated from the installed packages. Regenerate with `tools/licences.sh`.", ""]
for group, names in (("Shipped to the browser", runtime), ("Build tooling, not shipped", build)):
    out += [f"## {group}", ""]
    for n in names:
        pkg = root / n / "package.json"
        if not pkg.exists():
            out += [f"### {n}", "", "Not installed.", ""]; continue
        m = json.loads(pkg.read_text())
        out += [f"### {m['name']} {m.get('version','')}", "", f"Licence: {m.get('license','unknown')}", ""]
        for c in ("LICENSE","LICENSE.md","LICENCE","LICENSE.txt","license"):
            f = root / n / c
            if f.exists():
                out += ["```", f.read_text().strip(), "```", ""]; break
        else:
            out += ["Licence file not distributed with the package.", ""]
pathlib.Path("docs/third-party-licences.md").write_text("\n".join(out))
print("wrote docs/third-party-licences.md")
PY
