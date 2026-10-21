# System Architecture & Graph Topology

## 1. Overview & Data Flow

Astral Cartographer processes a repository through a deterministic pipeline:

```text
[ GitHub URL ]
      │
      ▼
[ Ingestor Service ]
  - Shallow Git clone
  - Noise filtering (.git, node_modules, tests, lockfiles, binaries)
  - Language detection (Python, JS, TS)
      │
      ▼
[ Multi-Language Parsers ]
  - AST parsing (Python ast, JS/TS regex/token parser)
  - Extracts classes, functions, methods, imports, calls
      │
      ▼
[ Cartographer Graph Engine ]
  - Builds NetworkX DiGraph
  - Creates nodes (Galaxy -> Systems -> Stars -> Planets -> Moons)
  - Computes PageRank (centrality) & Louvain modularity (communities)
  - Calculates 3D coordinate spherical/spiral distribution
      │
      ▼
[ AI Workflow Engine ]
  - Identifies entry points and key flow chains
  - Generates plain-English narrative of code execution paths
      │
      ▼
[ AstralGraph Schema Output ]
  - Serialized deterministic JSON for Three.js 3D rendering
```

---

## 2. Celestial Hierarchy (Node Types)

| Celestial Level | Node Type | Maps To in Codebase | Visual Meaning in 3D Galaxy |
|---|---|---|---|
| **Galaxy** | `galaxy` | The entire repository | Galaxy core |
| **System** | `system` | Top-level directory / architectural module | Star cluster / solar system |
| **Star** | `star` | Core source file / high-centrality module | Central star |
| **Planet** | `planet` | Major class or standalone module | Orbiting body |
| **Moon** | `moon` | Functions, methods, subroutines | Orbiting satellite |

---

## 3. Relationship Types (Edge Relations)

- `contains`: Hierarchical parent-child relationship (e.g. system contains file, class contains method).
- `imports`: Module dependency / import statement.
- `calls`: Function invocation or execution cross-reference.
- `inherits`: Class inheritance or interface implementation.

---

## 4. Graph Metrics & Physics

Each node contains calculated metrics:
- **`centrality`**: Computed via NetworkX PageRank (normalized between 0.0 and 1.0), controlling node glow and size in 3D.
- **`cluster_id`**: Louvain community detection identifier for color grouping.
- **`loc`**: Lines of code.
- **`size_bytes`**: Disk size in bytes.
