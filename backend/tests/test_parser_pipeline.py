"""End-to-end parser/resolver tests against a real on-disk fixture repository.

Asserts exact nodes, edge directions and diagnostics. Parsing runs inside a subprocess
so a native tree-sitter crash fails the test instead of killing pytest.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

BACKEND = Path(__file__).resolve().parents[1]

FIXTURE = {
    # --- JavaScript / TypeScript (ESM + CommonJS + tsconfig alias) ---
    "web/src/App.jsx": """
        import React from 'react';
        import Navbar from './components/Navbar.jsx';
        import { helper as h, helper } from './utils';
        import { helper as h2 } from './utils';
        import missing from './nope';
        import fs from 'node:fs';
        export default function App() { return Navbar(); }
    """,
    "web/src/components/Navbar.jsx": """
        import { helper } from '../utils';
        export default function Navbar() { return helper(); }
    """,
    "web/src/utils/index.js": "export function helper() { return 1; }\n",
    "web/src/cycle_a.js": "import './cycle_b';\nexport const a = 1;\n",
    "web/src/cycle_b.js": "import './cycle_a';\nexport const b = 1;\n",
    "web/src/feature.ts": "import { Thing } from '@/models/thing';\nexport const f = (t: Thing) => t;\n",
    "web/src/models/thing.ts": "export interface Thing { id: number }\n",
    "web/tsconfig.json": '{ // comment\n "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"] }, },\n}\n',
    "legacy/server.js": """
        const express = require('express');
        const { run, other: o } = require('./lib/runner');
        const util = require('./lib/util').format;
        require('./lib/side');
        module.exports = function start() { return run(); };
    """,
    "legacy/lib/runner.js": "exports.run = function run() { return 1; };\nexports.other = function other() {};\n",
    "legacy/lib/util.js": "module.exports = { format };\nfunction format() {}\n",
    "legacy/lib/side.js": "console.log('side');\n",
    "web/src/broken.js": "function (((( {\n",
    # --- Python ---
    "py/app/__init__.py": "",
    "py/app/main.py": """
        from . import models
        from .models import User as U
        from .services.auth import login
        import requests
        import os
        import app.models

        class Admin(U):
            def go(self):
                return login(self)
    """,
    "py/app/models.py": "class User:\n    pass\n",
    "py/app/services/__init__.py": "",
    "py/app/services/auth.py": "from app.models import User\n\ndef login(u: User):\n    return u\n",
    "py/app/cyc1.py": "from app import cyc2\n",
    "py/app/cyc2.py": "from app import cyc1\n",
    "notes.txt": "plain text",
    "data.bin.dat": "x",
}

RUN_SCRIPT = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[3])
    from app.services.analysis_pipeline import run_analysis
    diag = run_analysis(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({"ok": True}))
    """
)


class ParserPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(cls._tmp.name)
        cls.src, cls.out = root / "src", root / "out"
        for rel, body in FIXTURE.items():
            p = cls.src / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        script = root / "run.py"
        script.write_text(RUN_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(script), str(cls.src), str(cls.out), str(BACKEND)],
            capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        cls.graph = json.loads((cls.out / "code_graph.json").read_text(encoding="utf-8"))
        cls.diag = json.loads((cls.out / "diagnostics.json").read_text(encoding="utf-8"))
        cls.imports = {(e["source"], e["target"]) for e in cls.graph["edges"] if e["type"] == "IMPORTS"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def has(self, src: str, dst: str) -> bool:
        return (f"file:{src}", f"file:{dst}") in self.imports

    def test_esm_relative_and_index_resolution_with_direction(self) -> None:
        self.assertTrue(self.has("web/src/App.jsx", "web/src/components/Navbar.jsx"))
        self.assertTrue(self.has("web/src/App.jsx", "web/src/utils/index.js"))
        self.assertTrue(self.has("web/src/components/Navbar.jsx", "web/src/utils/index.js"))
        self.assertFalse(self.has("web/src/components/Navbar.jsx", "web/src/App.jsx"))

    def test_no_duplicate_edges_for_duplicate_imports(self) -> None:
        pairs = [(e["source"], e["target"], e["type"]) for e in self.graph["edges"]]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(sum(1 for e in self.graph["edges"] if e["type"] == "IMPORTS"
                             and e["source"] == "file:web/src/App.jsx" and e["target"] == "file:web/src/utils/index.js"), 1)

    def test_tsconfig_alias_resolves_and_bare_names_stay_external(self) -> None:
        self.assertTrue(self.has("web/src/feature.ts", "web/src/models/thing.ts"))
        refs = [u for u in self.graph["unresolved_references"] if u["kind"] == "import"]
        ext = {u["target_name"] for u in refs if u["status"] == "external"}
        self.assertTrue({"react", "express", "node:fs", "requests", "os"} <= ext)
        self.assertFalse(any(t.startswith("file:") and "react" in t for _, t in self.imports))

    def test_unresolved_internal_import_is_recorded_not_resolved(self) -> None:
        missing = [u for u in self.graph["unresolved_references"] if u["kind"] == "import" and u["status"] == "unresolved"]
        self.assertEqual([(u["source_file"], u["target_name"]) for u in missing], [("web/src/App.jsx", "./nope")])
        self.assertEqual(self.diag["dependencies"]["imports_unresolved"], 1)
        self.assertEqual(self.diag["unresolved_internal_imports"][0]["target"], "./nope")

    def test_commonjs_require_forms(self) -> None:
        for dst in ("legacy/lib/runner.js", "legacy/lib/util.js", "legacy/lib/side.js"):
            self.assertTrue(self.has("legacy/server.js", dst), dst)
        self.assertFalse(self.has("legacy/lib/runner.js", "legacy/server.js"))

    def test_commonjs_named_call_resolves_to_exported_function(self) -> None:
        calls = [e for e in self.graph["edges"] if e["type"] == "CALLS" and "legacy/lib/runner.js" in e["target"]]
        self.assertTrue(any("start" in e["source"] or e["source"] == "file:legacy/server.js" for e in calls), calls)

    def test_cycles_in_both_languages_terminate_and_are_edges(self) -> None:
        self.assertTrue(self.has("web/src/cycle_a.js", "web/src/cycle_b.js"))
        self.assertTrue(self.has("web/src/cycle_b.js", "web/src/cycle_a.js"))
        self.assertTrue(self.has("py/app/cyc1.py", "py/app/cyc2.py"))
        self.assertTrue(self.has("py/app/cyc2.py", "py/app/cyc1.py"))

    def test_python_relative_absolute_and_inheritance_resolution(self) -> None:
        self.assertTrue(self.has("py/app/main.py", "py/app/models.py"))
        self.assertTrue(self.has("py/app/main.py", "py/app/services/auth.py"))
        self.assertTrue(self.has("py/app/services/auth.py", "py/app/models.py"))
        names = {n["name"] for n in self.graph["nodes"] if n["type"] in ("class", "function", "method")}
        self.assertTrue({"Admin", "User", "login", "go"} <= names)

    def test_symbols_have_line_ranges(self) -> None:
        user = next(n for n in self.graph["nodes"] if n["type"] == "class" and n["name"] == "User")
        self.assertEqual(user["metadata"]["lineno"], 1)
        self.assertGreaterEqual(user["metadata"]["end_lineno"], 1)

    def test_folders_are_never_dependency_endpoints(self) -> None:
        for e in self.graph["edges"]:
            if e["type"] in ("IMPORTS", "CALLS"):
                self.assertFalse(e["source"].startswith(("directory:", "repository:")), e)
                self.assertFalse(e["target"].startswith(("directory:", "repository:")), e)

    def test_diagnostics_report_errors_and_unsupported_files(self) -> None:
        d = self.diag
        self.assertEqual(d["status"], "partial")
        self.assertEqual([e["file_path"] for e in d["syntax_errors"]], ["web/src/broken.js"])
        self.assertIn(".txt", d["files"]["unsupported_by_extension"])
        self.assertGreater(d["files"]["discovered"], 20)
        self.assertGreater(d["symbols"]["extracted"], 5)
        self.assertGreater(d["timings_ms"]["total"], 0)
        self.assertTrue(d["warnings"])

    def test_every_edge_endpoint_exists(self) -> None:
        ids = {n["id"] for n in self.graph["nodes"]}
        for e in self.graph["edges"]:
            self.assertIn(e["source"], ids)
            self.assertIn(e["target"], ids)


if __name__ == "__main__":
    unittest.main()
