"""Repositories API routes for ingestion, source reading, symbols, and graph queries."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.api.schemas import (
    DependenciesResponse,
    FileListResponse,
    GraphResponse,
    ImpactAnalysisResponse,
    RepositoryDetail,
    RepositoryListResponse,
    RepositorySubmitRequest,
    RepositorySubmitResponse,
    RepositorySummary,
    SourceFileResponse,
    SymbolSearchResponse,
    RepositoryAnalyticsResponse,
    ChatRequest,
    QAResponse,
    ClusterSummarizeRequest,
    ClusterSummarizeResponse,
    RepositoryClustersResponse,
    WorkflowListResponse,
    WorkflowTraceRequest,
    WorkflowTraceResponse,
)
from app.services.ai_client import AIError
from app.services.cluster_service import cluster_service
from app.services.github_app import session_from_authorization
from app.services.qa_service import qa_service
from app.services.workflow_service import workflow_service
from app.services.repository_service import (
    get_repository_analytics,
    get_repository_code_graph,
    get_repository_files,
    get_symbol_dependencies,
    get_symbol_impact_analysis,
    read_repository_source_file,
    search_repository_symbols,
    submit_repository_for_indexing,
    submit_zip_for_indexing,
)
from app.storage.repository_store import get_repository, list_repositories

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post(
    "",
    response_model=RepositorySubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a public GitHub repository for indexing",
)
def submit_repository(req: RepositorySubmitRequest) -> RepositorySubmitResponse:
    """Validate, register, and queue a public GitHub repository for indexing."""
    try:
        repo_rec, job_rec = submit_repository_for_indexing(
            url=req.url,
            branch=req.branch,
        )
        return RepositorySubmitResponse(
            repository_id=repo_rec.id,
            job_id=job_rec.id,
            status=job_rec.status,
            message="Repository indexing has been queued.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.exception("Failed to submit repository: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error queueing repository indexing",
        ) from err

@router.post(
    "/upload",
    response_model=RepositorySubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a repository ZIP archive for indexing",
)
async def upload_repository_zip(
    request: Request,
    branch: str = Query(default="main"),
    name: Optional[str] = Query(default=None),
    filename: Optional[str] = Query(default="repository.zip"),
) -> RepositorySubmitResponse:
    """Validate, register, and queue an uploaded repository ZIP archive for indexing."""
    try:
        content_type = request.headers.get("content-type", "")
        raw_body = await request.body()

        if raw_body.startswith(b"PK"):
            file_bytes = raw_body
        elif "multipart/form-data" in content_type:
            from email.parser import BytesParser
            from email.policy import default

            msg = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\n\r\n".encode("latin1") + raw_body
            )
            file_bytes = None
            for part in msg.iter_parts():
                payload = part.get_payload(decode=True)
                if payload and payload.startswith(b"PK"):
                    file_bytes = payload
                    if part.get_filename():
                        filename = part.get_filename()
                    break
            if file_bytes is None:
                raise ValueError("Could not find valid ZIP archive content in multipart upload")
        else:
            file_bytes = raw_body

        repo_rec, job_rec = submit_zip_for_indexing(
            file_bytes=file_bytes,
            filename=filename or "repository.zip",
            branch=branch,
            repo_name=name,
        )
        return RepositorySubmitResponse(
            repository_id=repo_rec.id,
            job_id=job_rec.id,
            status=job_rec.status,
            message="Repository ZIP archive uploaded and indexing has been queued.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.exception("Failed to process uploaded repository archive: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing repository archive",
        ) from err



@router.get(
    "",
    response_model=RepositoryListResponse,
    summary="List indexed repositories",
)
def get_repositories(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    authorization: Optional[str] = Header(default=None),
) -> RepositoryListResponse:
    """Retrieve paginated list of indexed repositories (plus the caller's own private ones)."""
    sess = session_from_authorization(authorization)
    repos = list_repositories(
        limit=limit, offset=offset, viewer_github_user_id=sess.user_id if sess else None
    )
    items = [RepositorySummary(**r.to_dict()) for r in repos]
    return RepositoryListResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{repository_id}",
    response_model=RepositoryDetail,
    summary="Get repository details",
)
def get_repository_detail(repository_id: str) -> RepositoryDetail:
    """Retrieve metadata, current status, and timestamps for a repository."""
    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' not found",
        )
    return RepositoryDetail(**repo.to_dict())


@router.get(
    "/{repository_id}/files",
    response_model=FileListResponse,
    summary="List files in an indexed repository",
)
def get_files(
    repository_id: str,
    language: Optional[str] = Query(default=None, description="Optional language filter"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FileListResponse:
    """Retrieve file inventory for a repository."""
    try:
        total, files = get_repository_files(
            repo_id=repository_id,
            language=language,
            limit=limit,
            offset=offset,
        )
        return FileListResponse(
            repository_id=repository_id,
            total_files=total,
            files=files,
        )
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/file",
    response_model=SourceFileResponse,
    summary="Read a repository source file safely",
)
def get_source_file(
    repository_id: str,
    path: str = Query(..., description="Relative repository source path"),
    start_line: Optional[int] = Query(default=None, ge=1),
    end_line: Optional[int] = Query(default=None, ge=1),
) -> SourceFileResponse:
    """Read source content with optional line slicing and strict traversal protection."""
    try:
        data = read_repository_source_file(
            repo_id=repository_id,
            rel_path=path,
            start_line=start_line,
            end_line=end_line,
        )
        return SourceFileResponse(**data)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except ValueError as err:
        # Check if size limit exceeded
        if "exceeds maximum" in str(err).lower():
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(err),
            ) from err
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/graph",
    response_model=GraphResponse,
    summary="Retrieve repository code graph",
)
def get_graph(
    repository_id: str,
    node_type: Optional[str] = Query(default=None, description="Filter by node type"),
    edge_type: Optional[str] = Query(default=None, description="Filter by edge type"),
    limit: Optional[int] = Query(default=None, ge=1, description="Limit node count"),
) -> GraphResponse:
    """Retrieve complete code graph nodes and edges for an indexed repository."""
    try:
        graph = get_repository_code_graph(
            repo_id=repository_id,
            node_type=node_type,
            edge_type=edge_type,
            limit=limit,
        )
        return GraphResponse(**graph)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/analytics",
    response_model=RepositoryAnalyticsResponse,
    summary="Retrieve repository graph analytics and intelligence",
)
def get_analytics(repository_id: str) -> RepositoryAnalyticsResponse:
    """Retrieve PageRank, degree centrality, community detection, and graph statistics."""
    try:
        data = get_repository_analytics(repository_id)
        return RepositoryAnalyticsResponse(**data)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.post(
    "/{repository_id}/chat",
    response_model=QAResponse,
    summary="Semantic codebase Q&A grounded in repository graph",
)
async def chat_repository(
    repository_id: str,
    req: ChatRequest,
) -> QAResponse:
    """Answer natural language architectural questions grounded in the repository's code graph."""
    try:
        return await qa_service.answer_question(
            repo_id=repository_id,
            question=req.question,
            history=req.history,
        )
    except AIError as err:
        raise HTTPException(status_code=err.status_code, detail=err.to_dict()) from err
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/clusters",
    response_model=RepositoryClustersResponse,
    summary="Explore Louvain community clusters",
)
def get_clusters(
    repository_id: str,
    cluster_id: Optional[int] = Query(default=None, description="Optional target cluster ID"),
) -> RepositoryClustersResponse:
    """Retrieve detected galaxy community clusters and any existing architectural summaries."""
    try:
        return cluster_service.get_repository_clusters(
            repo_id=repository_id,
            target_cluster_id=cluster_id,
        )
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.post(
    "/{repository_id}/clusters/summarize",
    response_model=ClusterSummarizeResponse,
    summary="Synthesize AI architectural summaries for community clusters",
)
async def summarize_clusters(
    repository_id: str,
    req: ClusterSummarizeRequest,
) -> ClusterSummarizeResponse:
    """Generate high-level architectural summaries for galaxy clusters using Gemini or heuristics."""
    try:
        return await cluster_service.summarize_repository_clusters(
            repo_id=repository_id,
            cluster_id=req.cluster_id,
            force_refresh=req.force_refresh,
        )
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/workflows",
    response_model=WorkflowListResponse,
    summary="Retrieve detected execution workflows",
)
async def get_workflows(
    repository_id: str,
) -> WorkflowListResponse:
    """Retrieve statically inferred execution workflows and call pathways."""
    try:
        workflows = workflow_service.get_repository_workflows(repository_id)
        if not workflows.workflows:
            trace_resp = await workflow_service.trace_repository_workflows(
                repo_id=repository_id,
                max_workflows=5,
            )
            return WorkflowListResponse(
                repository_id=repository_id,
                total_workflows=trace_resp.total_workflows,
                workflows=trace_resp.workflows,
            )
        return workflows
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.post(
    "/{repository_id}/workflows/trace",
    response_model=WorkflowTraceResponse,
    summary="Trace execution workflows across code graph",
)
async def trace_workflows(
    repository_id: str,
    req: WorkflowTraceRequest,
) -> WorkflowTraceResponse:
    """Discover entry points and trace static call and import pathways through the graph."""
    try:
        return await workflow_service.trace_repository_workflows(
            repo_id=repository_id,
            max_workflows=req.max_workflows,
            entry_point_query=req.entry_point_query,
            force_refresh=req.force_refresh,
        )
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/symbols",
    response_model=SymbolSearchResponse,
    summary="Search code symbols in repository",
)
def search_symbols(
    repository_id: str,
    q: str = Query(..., min_length=1, description="Symbol name search query"),
    kind: Optional[str] = Query(default=None, description="Filter by symbol kind"),
    language: Optional[str] = Query(default=None, description="Filter by language"),
    limit: int = Query(default=50, ge=1, le=200),
) -> SymbolSearchResponse:
    """Search extracted symbols across Python, JavaScript, and TypeScript."""
    try:
        symbols = search_repository_symbols(
            repo_id=repository_id,
            query=q,
            kind=kind,
            language=language,
            limit=limit,
        )
        return SymbolSearchResponse(
            repository_id=repository_id,
            query=q,
            total_matches=len(symbols),
            symbols=symbols,
        )
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/dependencies",
    response_model=DependenciesResponse,
    summary="Query symbol dependencies or callers",
)
def get_dependencies(
    repository_id: str,
    symbol_id: str = Query(..., description="Target symbol ID"),
    direction: str = Query(default="outgoing", description="'outgoing' or 'incoming'"),
    depth: int = Query(default=1, ge=0, le=10, description="Traversal depth"),
) -> DependenciesResponse:
    """Query outgoing dependencies or incoming callers for a symbol."""
    if direction not in ("outgoing", "incoming"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direction must be either 'outgoing' or 'incoming'",
        )

    try:
        data = get_symbol_dependencies(
            repo_id=repository_id,
            symbol_id=symbol_id,
            direction=direction,
            depth=depth,
        )
        return DependenciesResponse(**data)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/{repository_id}/impact",
    response_model=ImpactAnalysisResponse,
    summary="Perform change impact analysis for a symbol",
)
def get_impact(
    repository_id: str,
    symbol_id: str = Query(..., description="Target symbol ID to analyze"),
    max_depth: int = Query(default=5, ge=0, le=20, description="Maximum reverse traversal depth"),
) -> ImpactAnalysisResponse:
    """Perform change impact analysis by traversing reverse dependency edges."""
    try:
        data = get_symbol_impact_analysis(
            repo_id=repository_id,
            symbol_id=symbol_id,
            max_depth=max_depth,
        )
        return ImpactAnalysisResponse(**data)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get("/{repository_id}/diagnostics", summary="Parser diagnostics of the latest analysis")
def get_diagnostics(repository_id: str) -> dict:
    """Return persisted parser diagnostics (files parsed, errors, resolved/unresolved dependencies, timings)."""
    from app.storage.repository_store import get_latest_analysis

    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repository_id}' not found")
    analysis = get_latest_analysis(repo.id)
    if not analysis:
        raise HTTPException(status_code=409, detail=f"No completed analysis for repository (status: {repo.status})")
    return {"repository_id": repo.id, "analysis_id": analysis.id, "created_at": analysis.created_at,
            "graph_sha256": analysis.graph_sha256, "diagnostics": analysis.diagnostics}


@router.get("/{repository_id}/analyses", summary="Analysis history for a repository")
def get_analyses(repository_id: str, limit: int = Query(default=10, ge=1, le=50)) -> dict:
    from app.storage.repository_store import list_analyses

    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repository_id}' not found")
    items = [{k: v for k, v in a.to_dict().items() if k != "diagnostics"} for a in list_analyses(repo.id, limit)]
    return {"repository_id": repo.id, "items": items}


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a repository and its analysis data")
def delete_repository_endpoint(repository_id: str) -> None:
    from app.services.repository_service import delete_repository

    try:
        delete_repository(repository_id)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
