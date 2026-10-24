/**
 * Astral Cartographer — API Service Client
 * Connects the 3D frontend to the FastAPI backend endpoints (/api/v1/*)
 */

import {
  AstralGraph,
  ImpactAnalysisResult,
  JobStatus,
  QAResponse,
  RepositoryItem,
  Workflow,
} from '../types/galaxy'

const API_BASE = '/api/v1'

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`
    try {
      const errJson = await response.json()
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail)
      }
    } catch {
      // ignore
    }
    throw new ApiError(errorDetail, response.status)
  }

  return response.json()
}

/** Check backend health status */
export async function checkBackendHealth(): Promise<{ status: string; app: string; version: string }> {
  return request('/health')
}

/** Fetch the default bundled Demo Galaxy */
export async function fetchDemoGraph(): Promise<AstralGraph> {
  return request<AstralGraph>('/graph/demo')
}

/** Synchronously clone and analyze a GitHub repository */
export async function analyzeRepository(repoUrl: string, branch = 'main', includeAi = false): Promise<AstralGraph> {
  return request<AstralGraph>('/graph/analyze', {
    method: 'POST',
    body: JSON.stringify({
      repo_url: repoUrl,
      branch,
      include_ai_summary: includeAi,
    }),
  })
}

/** Submit a repository for background async indexing */
export async function submitRepositoryJob(repoUrl: string, branch = 'main'): Promise<{
  repository_id: string
  job_id: string
  status: string
  message: string
}> {
  return request('/repositories', {
    method: 'POST',
    body: JSON.stringify({
      repo_url: repoUrl,
      branch,
    }),
  })
}

/** Poll status of an async indexing job */
export async function checkJobStatus(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/jobs/${jobId}`)
}

/** List all previously indexed repositories */
export async function listRepositories(): Promise<RepositoryItem[]> {
  return request<RepositoryItem[]>('/repositories')
}

/** Fetch 3D graph for a specific repository ID */
export async function fetchRepositoryGraph(repoId: string): Promise<AstralGraph> {
  return request<AstralGraph>(`/repositories/${repoId}/graph`)
}

/** Ask natural language questions via LangGraph agent */
export async function askCodebaseQuestion(question: string, repoUrl?: string): Promise<QAResponse> {
  return request<QAResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({
      question,
      repo_url: repoUrl,
    }),
  })
}

/** Run execution workflow tracing ("glowing pulses") */
export async function traceWorkflows(maxWorkflows = 4): Promise<{
  status: string
  total_workflows: number
  workflows: Workflow[]
}> {
  return request('/analyze/workflows', {
    method: 'POST',
    body: JSON.stringify({ max_workflows: maxWorkflows }),
  })
}

/** Synthesize Galaxy cluster summaries */
export async function synthesizeClusters(): Promise<{
  total_clusters: number
  cluster_summaries: Record<number, string>
}> {
  return request('/analyze/clusters', {
    method: 'POST',
  })
}

/** Compute architectural impact blast radius for a target node */
export async function fetchImpactAnalysis(repoId: string, nodeId: string, maxDepth = 3): Promise<ImpactAnalysisResult> {
  return request<ImpactAnalysisResult>(
    `/repositories/${repoId}/impact?node_id=${encodeURIComponent(nodeId)}&max_depth=${maxDepth}`
  )
}
