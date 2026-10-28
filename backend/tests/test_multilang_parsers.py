"""JSX, TSX, Java, Kotlin and Rust: parser, resolver and graph tests on multi-file fixture projects.

Every fixture runs the real pipeline: scanner -> parser registry -> symbol resolver -> graph
builder -> serialization (the same ``run_analysis`` the indexing job uses).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.api.schemas import GraphResponse
from app.graph.graph_queries import get_incoming_neighbors, get_outgoing_neighbors
from app.graph.models import VALID_EDGE_TYPES
from app.ingestion.scanner import detect_language
from app.parsers import common
from app.parsers.java_parser import JAVA_SPEC, parse_java_source
from app.parsers.javascript_parser import get_language_and_parser, parse_js_source_code
from app.parsers.kotlin_parser import parse_kotlin_source
from app.parsers.registry import PARSER_BY_LANGUAGE, PARSER_SPECS, spec_for_language
from app.parsers.rust_parser import parse_rust_source, rust_module_path
from app.services.analysis_pipeline import run_analysis

FIXTURES = Path(__file__).resolve().parent / "fixtures_lang"
_CACHE: dict[str, "Analysis"] = {}


class Analysis:
    def __init__(self, source: Path) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.out = Path(self.tmp.name) / "artifacts"
        self.diag = run_analysis(source, self.out)
        self.graph = json.loads((self.out / "code_graph.json").read_text(encoding="utf-8"))
        self.nodes = {n["id"]: n for n in self.graph["nodes"]}
        self.edges = self.graph["edges"]

    def edge_set(self, etype: str) -> set[tuple[str, str]]:
        return {(self.short(e["source"]), self.short(e["target"])) for e in self.edges if e["type"] == etype}

    @staticmethod
    def short(node_id: str) -> str:
        """``symbol:path::Qual.name:kind:line`` -> ``path::Qual.name`` ; file ids drop the prefix."""
        if node_id.startswith("symbol:"):
            body = node_id[len("symbol:"):]
            path, _, rest = body.partition("::")
            qual = rest.rsplit(":", 2)[0]
            return f"{path}::{qual}"
        return node_id.split(":", 1)[1] if node_id.startswith("file:") else node_id

    def unresolved(self, kind: str, status: str) -> list[dict]:
        return [u for u in self.graph["unresolved_references"] if u["kind"] == kind and u["status"] == status]


def analysis(name: str) -> Analysis:
    if name not in _CACHE:
        _CACHE[name] = Analysis(FIXTURES / name)
    return _CACHE[name]


def tearDownModule() -> None:
    for a in _CACHE.values():
        a.tmp.cleanup()


J = "src/main/java/com/acme"
K = "src/main/kotlin/com/acme"


# ------------------------------------------------------------------ registry / scanner
class RegistryAndScannerTests(unittest.TestCase):
    def test_extensions_map_to_one_language_and_one_parser(self) -> None:
        expected = {".jsx": "JavaScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
                    ".rs": "Rust", ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript"}
        for ext, lang in expected.items():
            self.assertEqual(detect_language(Path(f"x{ext}")), lang, ext)
            self.assertIsNotNone(spec_for_language(lang))
        # each language is owned by exactly one parser, so no file can be parsed twice
        owners = [spec.key for spec in PARSER_SPECS for _ in spec.languages]
        self.assertEqual(len(owners), len(PARSER_BY_LANGUAGE))

    def test_tsx_uses_tsx_grammar_and_ts_does_not(self) -> None:
        jsx_src = b"const a = <div className='x'>{f()}</div>;\n"
        tsx = parse_js_source_code(jsx_src, "a.tsx")
        ts_plain = parse_js_source_code(jsx_src, "a.ts")
        jsx = parse_js_source_code(jsx_src, "a.jsx")
        self.assertEqual(tsx.errors, [])
        self.assertEqual(jsx.errors, [])
        self.assertTrue(ts_plain.errors, "plain .ts must not be parsed with the JSX grammar")
        self.assertIs(get_language_and_parser("a.tsx")[1].language, get_language_and_parser("b.tsx")[1].language)
        self.assertIsNot(get_language_and_parser("a.tsx")[1].language, get_language_and_parser("a.ts")[1].language)

    def test_each_parseable_file_is_parsed_exactly_once(self) -> None:
        a = analysis("mixed")
        inventory = json.loads((a.out / "repository_inventory.json").read_text(encoding="utf-8"))
        parseable = [f for f in inventory["files"] if spec_for_language(f["language"])]
        discovered = sum(v for spec in PARSER_SPECS for k, v in
                         json.loads((a.out / spec.filename).read_text(encoding="utf-8"))["summary"].items() if k.endswith("_files_discovered"))
        self.assertEqual(discovered, len(parseable))

    def test_empty_and_garbage_files_do_not_crash(self) -> None:
        for fn, path in ((parse_java_source, "A.java"), (parse_kotlin_source, "A.kt"), (parse_rust_source, "a.rs")):
            empty = fn(path, b"")
            self.assertEqual((empty.symbols, empty.errors), ([], []))
            broken = fn(path, b"\x00\xff{{{ fun class impl (((")
            self.assertTrue(broken.errors)  # reported, not raised

    def test_one_failing_file_does_not_abort_repository_analysis(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            root = Path(tmp)
            (root / "A.java").write_text("class A { void f() {} }\n")
            (root / "B.java").write_text("class B { void g() {} }\n")
            inv = root / "inv.json"
            inv.write_text(json.dumps({"files": [{"path": "A.java", "language": "Java"}, {"path": "B.java", "language": "Java"}]}))

            def flaky(path: str, src: bytes):
                if path == "A.java":
                    raise RuntimeError("boom")
                return parse_java_source(path, src)

            out = common.run_adapter(common.AdapterSpec("java", ("Java",), flaky), inv, root)
            self.assertEqual(out["summary"]["java_files_parsed"], 1)
            self.assertEqual(out["summary"]["files_with_errors"], 1)
            self.assertEqual([s["name"] for s in out["symbols"] if s["kind"] == "class"], ["B"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ JSX / TSX
class JsxTsxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = analysis("jsx")

    def test_component_usage_is_renders_not_calls(self) -> None:
        renders = self.a.edge_set("RENDERS")
        self.assertIn(("src/App.jsx::App", "src/components/Header.jsx::Header"), renders)
        self.assertIn(("src/App.jsx::App", "src/components/Card.jsx::Card"), renders)
        self.assertIn(("src/components/Card.jsx::Card", "src/components/Header.jsx::Header"), renders)
        self.assertIn(("src/App.jsx::Legacy.render", "src/components/Card.jsx::Card"), renders)  # class component
        calls = self.a.edge_set("CALLS")
        self.assertFalse(any(t.endswith("Header") for _, t in calls), "JSX usage must not be a CALLS edge")
        self.assertIn(("src/App.jsx::App", "src/App.jsx::format"), calls)  # a real call inside a JSX attribute

    def test_namespace_member_component_and_intrinsic_tags(self) -> None:
        self.assertIn(("src/App.jsx::App", "src/ui/index.jsx::Button"), self.a.edge_set("RENDERS"))  # <UI.Button />
        targets = {t for _, t in self.a.edge_set("RENDERS")}
        self.assertFalse(any("div" in t or "section" in t or "h1" in t for t in targets))

    def test_unresolved_component_is_recorded_not_invented(self) -> None:
        unresolved = [u for u in self.a.unresolved("relation", "unresolved") if "Unknown" in u["expression"]]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["source_file"], "src/App.jsx")
        self.assertFalse(any("Unknown" in n["name"] for n in self.a.nodes.values()))

    def test_heritage_external_and_internal(self) -> None:
        ext = [u["expression"] for u in self.a.unresolved("relation", "external")]
        self.assertIn("extends React.Component", ext)
        self.assertIn(("src/Typed.tsx::Props", "src/Typed.tsx::Base"), self.a.edge_set("EXTENDS"))

    def test_tsx_declarations_generics_and_type_annotations(self) -> None:
        names = {(n["type"], n["name"]) for n in self.a.nodes.values() if n["metadata"].get("file_path") == "src/Typed.tsx"}
        self.assertTrue({("interface", "Props"), ("interface", "Base"), ("class", "Panel"), ("function", "Typed")} <= names)
        self.assertIn(("src/Typed.tsx::Panel.render", "src/Typed.tsx::Typed"), self.a.edge_set("RENDERS"))  # <Typed<string> />
        called = {e["metadata"].get("callee") for e in self.a.edges if e["type"] == "CALLS"}
        self.assertFalse({"Box", "JSX.Element", "Props"} & called, "type annotations are not calls")

    def test_imports_resolve_with_and_without_extension(self) -> None:
        imports = self.a.edge_set("IMPORTS")
        self.assertIn(("src/App.jsx", "src/components/Card.jsx"), imports)  # './components/Card.jsx'
        self.assertIn(("src/App.jsx", "src/components/Header.jsx"), imports)  # './components/Header'
        self.assertIn(("src/App.jsx", "src/ui/index.jsx"), imports)  # './ui' -> index.jsx
        self.assertIn(("src/Typed.tsx", "src/components/Header.jsx"), imports)

    def test_malformed_jsx_is_file_level_error_only(self) -> None:
        self.assertEqual([e["file_path"] for e in self.a.diag["syntax_errors"]], ["src/Broken.jsx"])
        self.assertEqual(self.a.diag["status"], "partial")
        self.assertIn("src/App.jsx::App", {self.a.short(e["source"]) for e in self.a.edges if e["type"] == "RENDERS"})


# ------------------------------------------------------------------ Java
class JavaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = analysis("java")

    def test_symbols_kinds_ownership_and_overloads(self) -> None:
        ids = {n["metadata"].get("qualified_name"): n for n in self.a.nodes.values() if n["id"].startswith("symbol:")}
        for q in ("User", "User.Builder", "User.Level", "User.Point", "User.User(String)", "Svc", "Base"):
            self.assertIn(q, ids, q)
        self.assertEqual(ids["User.Builder"]["metadata"]["parent_scope"], "User")
        self.assertEqual(ids["User.Level"]["type"], "enum")
        self.assertEqual(ids["Svc"]["type"], "interface")
        g1, g2 = ids["User.greet(String)"], ids["User.greet(String,int)"]
        self.assertNotEqual(g1["id"], g2["id"])
        self.assertEqual((g1["metadata"]["lineno"], g2["metadata"]["lineno"]), (10, 15))
        self.assertEqual(g1["metadata"]["namespace"], "com.acme.model")
        self.assertIn(f"symbol:{J}/model/User.java::User.greet(String):method:10", self.a.nodes)

    def test_inheritance_edges(self) -> None:
        self.assertEqual(self.a.edge_set("EXTENDS"), {(f"{J}/model/User.java::User", f"{J}/model/Base.java::Base")})
        self.assertEqual(self.a.edge_set("IMPLEMENTS"), {(f"{J}/model/User.java::User", f"{J}/model/Svc.java::Svc")})

    def test_imports_including_static_and_wildcard(self) -> None:
        self.assertEqual(self.a.edge_set("IMPORTS"), {(f"{J}/app/Main.java", f"{J}/model/User.java"), (f"{J}/app/Main.java", f"{J}/util/Strings.java")})
        external = [u["expression"] for u in self.a.unresolved("import", "external")]
        self.assertIn("import org.external.Lib", external)

    def test_overloads_resolve_by_arity_and_inheritance(self) -> None:
        calls = self.a.edge_set("CALLS")
        main = f"{J}/app/Main.java::Main.main(String[])"
        self.assertIn((main, f"{J}/model/User.java::User.greet(String)"), calls)
        self.assertIn((main, f"{J}/model/User.java::User.greet(String,int)"), calls)  # distinct overload
        self.assertIn((main, f"{J}/model/Base.java::Base.id()"), calls)  # inherited
        self.assertIn((main, f"{J}/model/User.java::User.run()"), calls)
        self.assertIn((main, f"{J}/util/Strings.java::Strings.shout(String)"), calls)  # static import
        self.assertIn((main, f"{J}/app/Main.java::Main.helper()"), calls)  # same class
        self.assertIn((main, f"{J}/model/User.java::User"), calls)  # constructor -> class
        self.assertIn((f"{J}/model/User.java::User.greet(String)", f"{J}/model/Base.java::Base.touch()"), calls)  # inherited, unqualified
        self.assertIn((main, f"{J}/model/User.java::User.Builder"), calls)  # new User.Builder()

    def test_unresolved_and_external_calls_are_explicit(self) -> None:
        exprs = {u["expression"]: u["status"] for u in self.a.graph["unresolved_references"] if u["kind"] == "call"}
        self.assertEqual(exprs["Lib.go"], "external")
        self.assertEqual(exprs["Unknown.call"], "unresolved")
        self.assertEqual(self.a.diag["status"], "complete")


# ------------------------------------------------------------------ Kotlin
class KotlinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = analysis("kotlin")
        self.syms = {n["metadata"].get("qualified_name"): n for n in self.a.nodes.values() if n["id"].startswith("symbol:")}

    def test_declarations_and_top_level_ownership(self) -> None:
        for q in ("User", "Point", "Registry", "User.Companion", "User.greet(String)", "String.shout()", "helper(User)"):
            self.assertIn(q, self.syms, q)
        self.assertIsNone(self.syms["helper(User)"]["metadata"]["parent_scope"])  # top-level: no invented class owner
        self.assertIsNone(self.syms["String.shout()"]["metadata"]["parent_scope"])
        self.assertEqual(self.syms["String.shout()"]["metadata"]["signature"].split("(")[0], "fun String.shout")
        self.assertEqual(self.syms["User.Companion"]["metadata"]["parent_scope"], "User")
        self.assertEqual(self.syms["User.load()"]["type"], "method")
        self.assertTrue(self.syms["User.load()"]["metadata"]["is_async"])
        self.assertIn("data", self.syms["Point"]["metadata"]["decorators"])
        self.assertIn("object", self.syms["Registry"]["metadata"]["decorators"])

    def test_inheritance_is_classified_by_target_kind(self) -> None:
        self.assertEqual(self.a.edge_set("EXTENDS"), {(f"{K}/model/User.kt::User", f"{K}/model/Base.kt::Base")})
        self.assertEqual(self.a.edge_set("IMPLEMENTS"), {(f"{K}/model/User.kt::User", f"{K}/model/Svc.kt::Svc")})

    def test_alias_import_resolves(self) -> None:
        self.assertEqual(self.a.edge_set("IMPORTS"), {(f"{K}/app/Main.kt", f"{K}/model/User.kt"), (f"{K}/app/Main.kt", f"{K}/model/Svc.kt")})

    def test_calls_resolution(self) -> None:
        calls = self.a.edge_set("CALLS")
        main = f"{K}/app/Main.kt::main()"
        self.assertIn((main, f"{K}/model/User.kt::User.greet(String)"), calls)
        self.assertIn((main, f"{K}/model/Base.kt::Base.id()"), calls)  # inherited
        self.assertIn((main, f"{K}/model/User.kt::User.Companion.create()"), calls)  # User.create()
        self.assertIn((main, f"{K}/model/User.kt::helper(User)"), calls)
        self.assertIn((main, f"{K}/model/Svc.kt::Svc.run()"), calls)  # s: Service (alias) -> Svc.run
        self.assertIn((main, f"{K}/model/User.kt::Registry.size()"), calls)  # object
        self.assertIn((main, f"{K}/model/User.kt::User"), calls)  # constructor
        self.assertIn((f"{K}/model/User.kt::User.load()", f"{K}/model/User.kt::User.greet(String)"), calls)

    def test_external_and_unresolved(self) -> None:
        by_expr = {u["expression"]: u["status"] for u in self.a.graph["unresolved_references"] if u["kind"] == "call"}
        self.assertEqual(by_expr["println"], "external")
        self.assertEqual(by_expr["missing"], "unresolved")

    def test_extension_receiver_recorded(self) -> None:
        syms = json.loads((self.a.out / "kotlin_analysis.json").read_text(encoding="utf-8"))["symbols"]
        ext = next(s for s in syms if s["name"] == "shout")
        self.assertEqual(ext["receiver_type"], "String")
        self.assertIn("extension", ext["decorators"])


# ------------------------------------------------------------------ Rust
class RustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a = analysis("rust")

    def test_module_paths_are_crate_relative(self) -> None:
        self.assertEqual(rust_module_path("src/main.rs"), "crate")
        self.assertEqual(rust_module_path("src/models/mod.rs"), "crate::models")
        self.assertEqual(rust_module_path("src/models/role.rs"), "crate::models::role")
        self.assertEqual(rust_module_path("crates/x/src/a/b.rs"), "crate::a::b")

    def test_symbol_kinds_and_function_vs_method_vs_associated(self) -> None:
        by = {n["metadata"]["qualified_name"]: n for n in self.a.nodes.values() if n["id"].startswith("symbol:")}
        self.assertEqual(by["User"]["type"], "class")
        self.assertIn("struct", by["User"]["metadata"]["decorators"])
        self.assertEqual(by["Greeter"]["type"], "interface")
        self.assertEqual(by["Role"]["type"], "enum")
        self.assertEqual(by["User::new"]["type"], "function")  # associated function (no self)
        self.assertIn("associated", by["User::new"]["metadata"]["decorators"])
        self.assertEqual(by["User::greet"]["type"], "method")  # takes &self
        self.assertEqual(by["User::new"]["metadata"]["parent_scope"], "User")
        self.assertEqual(by["helper"]["type"], "function")
        self.assertIsNone(by["helper"]["metadata"]["parent_scope"])

    def test_imports_mods_and_reexports(self) -> None:
        imports = self.a.edge_set("IMPORTS")
        self.assertIn(("src/main.rs", "src/models/mod.rs"), imports)  # mod models; / use models::User
        self.assertIn(("src/main.rs", "src/util.rs"), imports)
        self.assertIn(("src/models/mod.rs", "src/models/role.rs"), imports)  # pub mod role;
        self.assertIn(("src/main.rs", "src/models/role.rs"), imports)  # use models::Role as R (through `pub use`)
        self.assertIn("use std::collections::HashMap", [u["expression"] for u in self.a.unresolved("import", "external")])

    def test_trait_impl_relation(self) -> None:
        self.assertEqual(self.a.edge_set("IMPLEMENTS"), {("src/models/mod.rs::User", "src/models/mod.rs::Greeter")})

    def test_calls_paths_associated_and_methods(self) -> None:
        calls = self.a.edge_set("CALLS")
        self.assertIn(("src/main.rs::main", "src/models/mod.rs::User::new"), calls)  # User::new via `use`
        self.assertIn(("src/main.rs::main", "src/models/mod.rs::User::greet"), calls)  # u inferred as User
        self.assertIn(("src/main.rs::main", "src/util.rs::helper"), calls)
        self.assertIn(("src/main.rs::main", "src/util.rs::other"), calls)  # crate::util::other

    def test_macros_are_never_resolved(self) -> None:
        by = {u["expression"]: (u["status"], u["reason"]) for u in self.a.graph["unresolved_references"] if u["kind"] == "call"}
        self.assertEqual(by["println!"][0], "external")
        self.assertEqual(by["missing::call"][0], "external")
        self.assertFalse(any(e["metadata"].get("callee", "").endswith("!") for e in self.a.edges if e["type"] == "CALLS"))

    def test_parse_without_cargo_build_and_user_macro_message(self) -> None:
        res = parse_rust_source("src/lib.rs", b"macro_rules! m { () => {} }\nfn f() { my_macro!(1); }\n")
        self.assertEqual(res.errors, [])
        call = next(c for c in res.calls if c.call_kind == "macro_call")
        self.assertEqual(call.callee, "my_macro!")


# ------------------------------------------------------------------ cross-cutting
class GraphIntegrityTests(unittest.TestCase):
    NAMES = ("jsx", "java", "kotlin", "rust")

    def test_valid_endpoints_unique_ids_and_known_edge_types(self) -> None:
        for name in self.NAMES:
            a = analysis(name)
            with self.subTest(name):
                self.assertEqual(len(a.nodes), len(a.graph["nodes"]), "duplicate node ids")
                edge_ids = [e["id"] for e in a.edges]
                self.assertEqual(len(edge_ids), len(set(edge_ids)), "duplicate edge ids")
                triples = [(e["source"], e["target"], e["type"]) for e in a.edges]
                self.assertEqual(len(triples), len(set(triples)))
                invalid = [e for e in a.edges if e["source"] not in a.nodes or e["target"] not in a.nodes]
                self.assertEqual(invalid, [])
                self.assertTrue({e["type"] for e in a.edges} <= VALID_EDGE_TYPES)
                for e in a.edges:
                    if e["type"] in ("EXTENDS", "IMPLEMENTS", "RENDERS", "CALLS", "IMPORTS"):
                        self.assertEqual(e["metadata"]["resolution_status"], "resolved")

    def test_locations_and_language_metadata(self) -> None:
        for name, lang in (("java", "java"), ("kotlin", "kotlin"), ("rust", "rust")):
            for n in analysis(name).nodes.values():
                if n["id"].startswith("symbol:"):
                    m = n["metadata"]
                    self.assertEqual(m["language"], lang)
                    self.assertGreaterEqual(m["lineno"], 1)
                    self.assertGreaterEqual(m["end_lineno"], m["lineno"])
                    self.assertIsNotNone(m["col_offset"])
                    self.assertEqual(m["file_path"], n["id"].split("::", 1)[0][len("symbol:"):])

    def test_output_is_deterministic_and_reindexing_does_not_duplicate(self) -> None:
        for name in self.NAMES:
            first = analysis(name)
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                out = Path(tmp) / "a"
                run_analysis(FIXTURES / name, out)
                run_analysis(FIXTURES / name, out)  # re-index into the same artifact directory
                again = json.loads((out / "code_graph.json").read_text(encoding="utf-8"))
            with self.subTest(name):
                self.assertEqual(again["nodes"], first.graph["nodes"])
                self.assertEqual(again["edges"], first.graph["edges"])
                self.assertEqual(again["unresolved_references"], first.graph["unresolved_references"])

    def test_serializes_through_api_models_and_filters_work(self) -> None:
        for name in self.NAMES:
            a = analysis(name)
            payload = {"repository_id": "r", "schema_version": a.graph["schema_version"], "summary": a.graph["summary"],
                       "nodes": a.graph["nodes"], "edges": a.graph["edges"], "unresolved_references": a.graph["unresolved_references"]}
            with self.subTest(name):
                GraphResponse(**payload)
        j = analysis("java")
        user = next(n for n in j.nodes if n.endswith("User:class:3"))
        self.assertEqual([n["name"] for n in get_outgoing_neighbors(j.graph, user, edge_type="EXTENDS")], ["Base"])
        base = next(n for n in j.nodes if n.endswith("Base:class:3"))
        self.assertEqual([n["name"] for n in get_incoming_neighbors(j.graph, base, edge_type="EXTENDS")], ["User"])
        self.assertEqual(get_outgoing_neighbors(j.graph, user, edge_type="RENDERS"), [])

    def test_diagnostics_count_new_relations(self) -> None:
        d = analysis("jsx").diag
        self.assertGreater(d["dependencies"]["relations_resolved"], 0)
        self.assertEqual(d["files"]["with_syntax_errors"], 1)
        self.assertIn("java", analysis("java").diag["files"]["parsed_by_language"])


class MixedRepositoryTest(unittest.TestCase):
    def test_all_languages_in_one_repository(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            src = Path(tmp) / "mono"
            for name in ("java", "kotlin", "rust", "jsx", "mixed"):
                shutil.copytree(FIXTURES / name, src / name)
            (src / "py").mkdir()
            (src / "py" / "svc.py").write_text("from py import util\n\nclass A:\n    def f(self):\n        return util.g()\n")
            (src / "py" / "util.py").write_text("def g():\n    return 1\n")
            (src / "py" / "__init__.py").write_text("")
            a = Analysis(src)
            try:
                langs = {n["metadata"]["language"] for n in a.nodes.values() if n["type"] == "file"}
                for lang in ("Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Rust"):
                    self.assertIn(lang, langs)
                analyzed = {n["metadata"]["language"] for n in a.nodes.values() if n["type"] == "file" and n["metadata"].get("analyzed")}
                self.assertTrue({"Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Rust"} <= analyzed)
                self.assertEqual([e for e in a.edges if e["source"] not in a.nodes or e["target"] not in a.nodes], [])
                self.assertIn(("py/svc.py", "py/util.py"), a.edge_set("IMPORTS"))
                self.assertTrue(a.edge_set("EXTENDS") and a.edge_set("IMPLEMENTS") and a.edge_set("RENDERS"))
                self.assertGreaterEqual(len(a.diag["files"]["parsed_by_language"]), 5)
            finally:
                a.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
