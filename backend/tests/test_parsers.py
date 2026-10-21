"""Tests for the Python and JS/TS source code parsers."""

from __future__ import annotations

from app.services.parsers.js_parser import JSParser
from app.services.parsers.python_parser import PythonParser


# ===================================================================
# Python Parser Tests
# ===================================================================

class TestPythonParser:
    """Tests for the Python AST parser."""

    def setup_method(self) -> None:
        self.parser = PythonParser()

    def test_supported_extensions(self) -> None:
        assert ".py" in self.parser.supported_extensions

    def test_extracts_functions(self) -> None:
        source = '''
def hello():
    pass

async def async_hello():
    pass
'''
        result = self.parser.parse_file("test.py", source, set())
        func_names = [s.name for s in result.symbols if s.kind == "function"]
        assert "hello" in func_names
        assert "async_hello" in func_names

    def test_extracts_classes_with_bases(self) -> None:
        source = '''
class Animal:
    pass

class Dog(Animal):
    pass

class GoldenRetriever(Dog):
    pass
'''
        result = self.parser.parse_file("models.py", source, set())
        classes = {s.name: s for s in result.symbols if s.kind == "class"}

        assert "Animal" in classes
        assert classes["Animal"].bases == []
        assert "Dog" in classes
        assert classes["Dog"].bases == ["Animal"]
        assert "GoldenRetriever" in classes
        assert classes["GoldenRetriever"].bases == ["Dog"]

    def test_extracts_imports(self) -> None:
        source = '''
import os
import sys
from pathlib import Path
'''
        result = self.parser.parse_file("test.py", source, set())
        assert len(result.imports) == 3

    def test_resolves_internal_imports(self) -> None:
        repo_files = {"app/utils.py", "app/models.py", "app/__init__.py"}
        source = '''
from app.utils import helper
from app.models import User
'''
        result = self.parser.parse_file("app/main.py", source, repo_files)
        resolved = [imp.resolved_path for imp in result.imports if imp.resolved_path]
        assert "app/utils.py" in resolved
        assert "app/models.py" in resolved

    def test_resolves_relative_imports(self) -> None:
        repo_files = {"pkg/utils.py", "pkg/sub/helper.py", "pkg/__init__.py"}
        source = '''
from .utils import foo
from .sub.helper import bar
'''
        result = self.parser.parse_file("pkg/main.py", source, repo_files)
        resolved = [imp.resolved_path for imp in result.imports if imp.resolved_path]
        assert "pkg/utils.py" in resolved
        assert "pkg/sub/helper.py" in resolved

    def test_external_imports_resolve_to_none(self) -> None:
        source = '''
import numpy
from flask import Flask
'''
        result = self.parser.parse_file("test.py", source, set())
        for imp in result.imports:
            assert imp.resolved_path is None

    def test_handles_syntax_errors_gracefully(self) -> None:
        source = "def broken(:\n    pass"
        result = self.parser.parse_file("bad.py", source, set())
        assert result.file_path == "bad.py"
        assert result.symbols == []
        assert result.imports == []

    def test_counts_loc(self) -> None:
        source = '''
# comment
def foo():
    pass

# blank lines don't count


'''
        result = self.parser.parse_file("test.py", source, set())
        assert result.loc == 4  # "# comment", "def foo():", "pass", "# blank lines don't count"


# ===================================================================
# JS/TS Parser Tests
# ===================================================================

class TestJSParser:
    """Tests for the JS/TS regex parser."""

    def setup_method(self) -> None:
        self.parser = JSParser()

    def test_supported_extensions(self) -> None:
        exts = self.parser.supported_extensions
        assert ".js" in exts
        assert ".ts" in exts
        assert ".tsx" in exts

    def test_extracts_function_declarations(self) -> None:
        source = '''
function handleRequest(req, res) {
    return res.json({});
}

async function fetchData() {
    return await fetch('/api');
}
'''
        result = self.parser.parse_file("server.js", source, set())
        func_names = [s.name for s in result.symbols if s.kind == "function"]
        assert "handleRequest" in func_names
        assert "fetchData" in func_names

    def test_extracts_arrow_functions(self) -> None:
        source = '''
const processItem = (item) => {
    return item.transform();
};

const fetchUser = async (id) => {
    return await db.find(id);
};
'''
        result = self.parser.parse_file("utils.js", source, set())
        func_names = [s.name for s in result.symbols if s.kind == "function"]
        assert "processItem" in func_names
        assert "fetchUser" in func_names

    def test_extracts_classes_with_extends(self) -> None:
        source = '''
class Component {
    render() {}
}

class Button extends Component {
    render() {}
}

export default class App extends Component {
    render() {}
}
'''
        result = self.parser.parse_file("components.tsx", source, set())
        classes = {s.name: s for s in result.symbols if s.kind == "class"}

        assert "Component" in classes
        assert classes["Component"].bases == []
        assert "Button" in classes
        assert classes["Button"].bases == ["Component"]
        assert "App" in classes
        assert classes["App"].bases == ["Component"]

    def test_extracts_esm_imports(self) -> None:
        source = '''
import React from 'react';
import { useState, useEffect } from 'react';
import './styles.css';
'''
        result = self.parser.parse_file("app.tsx", source, set())
        raw_specs = [imp.raw_statement for imp in result.imports]
        assert "react" in raw_specs
        assert "./styles.css" in raw_specs

    def test_extracts_require_imports(self) -> None:
        source = '''
const express = require('express');
const path = require('path');
const utils = require('./utils');
'''
        result = self.parser.parse_file("server.js", source, set())
        assert len(result.imports) >= 3

    def test_resolves_relative_imports(self) -> None:
        repo_files = {"src/utils.js", "src/components/Button.tsx"}
        source = '''
import { helper } from './utils';
import Button from './components/Button';
'''
        result = self.parser.parse_file("src/app.js", source, repo_files)
        resolved = [imp.resolved_path for imp in result.imports if imp.resolved_path]
        assert "src/utils.js" in resolved

    def test_resolves_imports_with_extension_probing(self) -> None:
        repo_files = {"src/helpers.ts", "src/config.js"}
        source = '''
import { foo } from './helpers';
import config from './config';
'''
        result = self.parser.parse_file("src/main.ts", source, repo_files)
        resolved = [imp.resolved_path for imp in result.imports if imp.resolved_path]
        assert "src/helpers.ts" in resolved
        assert "src/config.js" in resolved

    def test_resolves_index_imports(self) -> None:
        repo_files = {"src/components/index.ts"}
        source = "import { Button } from './components';"
        result = self.parser.parse_file("src/app.ts", source, repo_files)
        resolved = [imp.resolved_path for imp in result.imports if imp.resolved_path]
        assert "src/components/index.ts" in resolved

    def test_detects_typescript_language(self) -> None:
        result = self.parser.parse_file("app.tsx", "const x = 1;", set())
        assert result.language == "typescript"

    def test_detects_javascript_language(self) -> None:
        result = self.parser.parse_file("app.js", "const x = 1;", set())
        assert result.language == "javascript"
