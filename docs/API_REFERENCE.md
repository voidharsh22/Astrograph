# API Reference & Schemas

## Base URL
Default: `http://localhost:8000/api/v1`

---

## 1. Healthcheck

- **Path**: `/health`
- **Method**: `GET`
- **Response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

---

## 2. Demo Galaxy Graph

- **Path**: `/graph/demo`
- **Method**: `GET`
- **Description**: Returns a deterministic sample 3D galaxy graph formatted for Three.js frontend testing.
- **Response Schema**: `AstralGraph`

---

## 3. Ingestion & Analysis

- **Path**: `/graph/analyze`
- **Method**: `POST`
- **Request Body**:
```json
{
  "repo_url": "https://github.com/fastapi/fastapi",
  "branch": "main",
  "include_ai_summary": true
}
```
- **Response**:
```json
{
  "task_id": "c7a8b9f0-1234-5678-90ab-cdef12345678",
  "status": "pending",
  "message": "Analysis started. Connect to WebSocket for progress updates."
}
```

---

## 4. WebSocket Progress Stream

- **Path**: `/graph/ws/{task_id}`
- **Protocol**: WebSocket
- **Streaming Event Payloads**:
```json
{"stage": "cloning", "progress": 20, "message": "Cloning repository..."}
{"stage": "parsing", "progress": 50, "message": "Parsing AST files..."}
{"stage": "graph_building", "progress": 80, "message": "Constructing graph topology..."}
{"stage": "complete", "progress": 100, "result": { ...AstralGraph... }}
```
