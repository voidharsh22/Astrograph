// Service layer for workspace, indexing, graph data, and AI interactions.
// Supports both live backend (FastAPI /api/v1) and offline fallback mode with mock data.

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

// Mock fallback graph representing cosmic-weather-api (matches backend demo_galaxy.json)
export const MOCK_GRAPH = {
  repo_url: "https://github.com/astral-demo/cosmic-weather-api",
  repo_name: "cosmic-weather-api",
  branch: "main",
  commit_sha: "a1b2c3d4e5f6789012345678abcdef0123456789",
  generated_at: new Date().toISOString(),
  nodes: [
    {
      id: "dir::src",
      label: "src",
      type: "directory",
      language: null,
      path: "src",
      metrics: { loc: 1450, centrality: 0.85, complexity: 12.0 },
      position_hint: { cluster_id: 0, depth: 0 },
      ai_summary: "Root source directory containing the main application modules and routing."
    },
    {
      id: "dir::src/api",
      label: "api",
      type: "directory",
      language: null,
      path: "src/api",
      metrics: { loc: 420, centrality: 0.65, complexity: 6.5 },
      position_hint: { cluster_id: 1, depth: 1 },
      ai_summary: "HTTP API layer with FastAPI routers, middleware, and request validation."
    },
    {
      id: "dir::src/services",
      label: "services",
      type: "directory",
      language: null,
      path: "src/services",
      metrics: { loc: 680, centrality: 0.78, complexity: 18.2 },
      position_hint: { cluster_id: 2, depth: 1 },
      ai_summary: "Core business logic, astronomical data calculations, and telemetry caching."
    },
    {
      id: "dir::src/models",
      label: "models",
      type: "directory",
      language: null,
      path: "src/models",
      metrics: { loc: 210, centrality: 0.42, complexity: 3.1 },
      position_hint: { cluster_id: 3, depth: 1 },
      ai_summary: "Pydantic domain models, database schemas, and serialization entities."
    },
    {
      id: "file::src/main.py",
      label: "main.py",
      type: "file",
      language: "python",
      path: "src/main.py",
      metrics: { loc: 110, centrality: 0.92, complexity: 5.0 },
      position_hint: { cluster_id: 1, depth: 1 },
      ai_summary: "Entry point bootstrapping FastAPI server and registering event handlers."
    },
    {
      id: "func::src/main.py::create_app",
      label: "create_app()",
      type: "function",
      language: "python",
      path: "src/main.py",
      metrics: { loc: 35, centrality: 0.88, complexity: 4.0 },
      position_hint: { cluster_id: 1, depth: 2 },
      ai_summary: "Application factory configuring CORS, routing, and lifecycle states."
    },
    {
      id: "file::src/services/weather.py",
      label: "weather.py",
      type: "file",
      language: "python",
      path: "src/services/weather.py",
      metrics: { loc: 320, centrality: 0.74, complexity: 14.0 },
      position_hint: { cluster_id: 2, depth: 2 },
      ai_summary: "Calculates solar wind speeds, geomagnetic storm indexes, and orbital friction."
    },
    {
      id: "class::src/services/weather.py::SolarFluxEngine",
      label: "SolarFluxEngine",
      type: "class",
      language: "python",
      path: "src/services/weather.py",
      metrics: { loc: 160, centrality: 0.68, complexity: 11.5 },
      position_hint: { cluster_id: 2, depth: 3 },
      ai_summary: "Engine computing ionospheric density profiles and flare forecasts."
    },
    {
      id: "file::src/models/telemetry.py",
      label: "telemetry.py",
      type: "file",
      language: "python",
      path: "src/models/telemetry.py",
      metrics: { loc: 140, centrality: 0.50, complexity: 2.5 },
      position_hint: { cluster_id: 3, depth: 2 },
      ai_summary: "Validation schemas for deep space satellite readings and time-series metrics."
    },
    {
      id: "file::src/api/routes.py",
      label: "routes.py",
      type: "file",
      language: "python",
      path: "src/api/routes.py",
      metrics: { loc: 180, centrality: 0.70, complexity: 6.0 },
      position_hint: { cluster_id: 1, depth: 2 },
      ai_summary: "Endpoints serving realtime cosmic telemetry and historical lookups."
    }
  ],
  edges: [
    { id: "e1", source: "dir::src", target: "dir::src/api", relation: "contains", weight: 1.0 },
    { id: "e2", source: "dir::src", target: "dir::src/services", relation: "contains", weight: 1.0 },
    { id: "e3", source: "dir::src", target: "dir::src/models", relation: "contains", weight: 1.0 },
    { id: "e4", source: "dir::src", target: "file::src/main.py", relation: "contains", weight: 1.0 },
    { id: "e5", source: "file::src/main.py", target: "func::src/main.py::create_app", relation: "contains", weight: 1.0 },
    { id: "e6", source: "file::src/main.py", target: "file::src/api/routes.py", relation: "imports", weight: 2.0 },
    { id: "e7", source: "file::src/api/routes.py", target: "file::src/services/weather.py", relation: "calls", weight: 2.5 },
    { id: "e8", source: "file::src/services/weather.py", target: "class::src/services/weather.py::SolarFluxEngine", relation: "contains", weight: 1.5 },
    { id: "e9", source: "file::src/services/weather.py", target: "file::src/models/telemetry.py", relation: "imports", weight: 1.8 }
  ],
  workflows: [
    {
      name: "Cosmic Telemetry Ingestion Flow",
      description: "Lifecycle of an incoming sensor reading from HTTP router through physics computation and storage.",
      nodes: [
        "file::src/api/routes.py",
        "file::src/services/weather.py",
        "class::src/services/weather.py::SolarFluxEngine",
        "file::src/models/telemetry.py"
      ]
    }
  ]
};

// Fetch repository graph (3D galaxy schema)
export async function getRepositoryGraph(repoIdOrUrl) {
  try {
    const res = await fetch(`${BASE}/api/v1/repositories/${encodeURIComponent(repoIdOrUrl)}/graph`);
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    // backend not running or error
  }

  // Try demo endpoint
  try {
    const demoRes = await fetch(`${BASE}/api/v1/graph/demo`);
    if (demoRes.ok) {
      return await demoRes.json();
    }
  } catch (err) {
    // ignore
  }

  // Fallback to local mock data
  return MOCK_GRAPH;
}

// Queue repository for indexing
export async function submitRepositoryIndexing(repoUrl, branch = "main", userId = null, userEmail = null) {
  try {
    const res = await fetch(`${BASE}/api/v1/repositories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_url: repoUrl,
        branch,
        user_id: userId,
        user_email: userEmail
      })
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    // ignore
  }

  // Mock return
  return {
    repository_id: "repo-mock-" + Date.now().toString(36),
    job_id: "job-mock-" + Date.now().toString(36),
    status: "indexing",
    message: "Indexing initiated (Demo / Mock mode)"
  };
}

// Poll job status
export async function getJobStatus(jobId) {
  try {
    const res = await fetch(`${BASE}/api/v1/jobs/${jobId}`);
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    // ignore
  }

  return {
    id: jobId,
    status: "completed",
    progress: 100,
    current_stage: "Graph Ready"
  };
}

// Server-Sent Events stream URL for real-time progress events
export function getJobStreamUrl(jobId) {
  return `${BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/stream`;
}

// Ask codebase AI question
export async function askCodebaseQuestion(question, repoId) {
  try {
    const res = await fetch(`${BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, repo_id: repoId })
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    // backend not reached -> fallback to mock responder
  }

  const q = question.toLowerCase().trim();

  // Keyword matchers for different modules and concepts
  if (q.includes("weather") || q.includes("solar") || q.includes("flux") || q.includes("engine") || q.includes("physics") || q.includes("friction")) {
    return {
      answer: `Physics and atmospheric calculations are conducted in **\`src/services/weather.py\`** via the \`SolarFluxEngine\` class. It calculates real-time solar wind density, ionospheric atmospheric drag, and geomagnetic storm disturbance levels.`,
      confidence: 0.95,
      highlighted_node_ids: ["file::src/services/weather.py", "class::src/services/weather.py::SolarFluxEngine"]
    };
  }

  if (q.includes("model") || q.includes("schema") || q.includes("data") || q.includes("telemetry") || q.includes("packet") || q.includes("database")) {
    return {
      answer: `Data structures and serialization schemas are defined in **\`src/models/telemetry.py\`**. It contains Pydantic models for incoming satellite readings, instrument metrics, and sensor status fields.`,
      confidence: 0.93,
      highlighted_node_ids: ["file::src/models/telemetry.py"]
    };
  }

  if (q.includes("api") || q.includes("route") || q.includes("endpoint") || q.includes("http") || q.includes("url") || q.includes("request")) {
    return {
      answer: `HTTP routing is implemented in **\`src/api/routes.py\`**. It exposes endpoints for real-time telemetry streaming and historical orbital telemetry querying, delegating heavy logic to \`weather.py\`.`,
      confidence: 0.96,
      highlighted_node_ids: ["file::src/api/routes.py", "dir::src/api"]
    };
  }

  if (q.includes("workflow") || q.includes("pipeline") || q.includes("flow") || q.includes("lifecycle") || q.includes("trace")) {
    return {
      answer: `The primary execution pipeline is the **Cosmic Telemetry Ingestion Flow**:\n1. Inbound sensor packet arrives at **\`src/api/routes.py\`**\n2. Routed into **\`src/services/weather.py\`**\n3. Computed by **\`SolarFluxEngine\`**\n4. Validated and persisted through schemas in **\`src/models/telemetry.py\`**.`,
      confidence: 0.98,
      highlighted_node_ids: [
        "file::src/api/routes.py",
        "file::src/services/weather.py",
        "class::src/services/weather.py::SolarFluxEngine",
        "file::src/models/telemetry.py"
      ]
    };
  }

  if (q.includes("dir") || q.includes("folder") || q.includes("structure") || q.includes("architecture") || q.includes("overview")) {
    return {
      answer: `The repository architecture consists of 3 primary modules under **\`src/\`**:\n- **\`api/\`**: REST controllers and routing endpoints.\n- **\`services/\`**: Core domain logic and the \`SolarFluxEngine\`.\n- **\`models/\`**: Telemetry and data schemas.`,
      confidence: 0.92,
      highlighted_node_ids: ["dir::src", "dir::src/api", "dir::src/services", "dir::src/models"]
    };
  }

  if (q.includes("entry") || q.includes("start") || q.includes("main") || q.includes("bootstrap") || q.includes("run")) {
    return {
      answer: `The main entry point is **\`src/main.py\`**, which boots the application using the \`create_app()\` factory, configures middlewares, and mounts the API routes.`,
      confidence: 0.95,
      highlighted_node_ids: ["file::src/main.py", "func::src/main.py::create_app"]
    };
  }

  // Adaptive response for general questions
  return {
    answer: `Regarding *"**${question}**"*: In this repository architecture, execution flows from the HTTP routes in **\`src/api/routes.py\`** into **\`src/services/weather.py\`** (\`SolarFluxEngine\`), validated against telemetry models in **\`src/models/telemetry.py\`**.`,
    confidence: 0.88,
    highlighted_node_ids: ["file::src/main.py", "file::src/api/routes.py", "file::src/services/weather.py"]
  };
}

