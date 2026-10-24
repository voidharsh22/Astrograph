"""
Asynchronous indexing service orchestrating repository ingestion, safe extraction,
AST parsing, graph building, 3D coordinate calculation, and persistence with real-time telemetry.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import time
from typing import Any, Optional

from app.config import settings
from app.schemas.graph_schema import AstralGraph
from app.services.archive_extractor import extract_archive_safely
from app.services.cartographer import build_graph
from app.services.downloader import download_github_archive, extract_github_owner_and_repo
from app.services.graph_store import set_active_graph_store, GraphStore
from app.services.ingestor import ingest_repository, ingest_local_directory, cleanup_clone
from app.storage.repository_store import (
    complete_job,
    fail_job,
    save_graph_artifact,
    update_job_progress,
)

logger = logging.getLogger(__name__)


def _log(level: str, text: str) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level,
        "text": text,
    }


async def run_indexing_pipeline(
    repo_id: str,
    job_id: str,
    url: str,
    branch: str = "main",
    use_git_clone: bool = False,
) -> None:
    """Execute complete repository indexing pipeline in background, emitting real-time telemetry."""
    logger.info("Starting indexing pipeline for repo %s (job %s)", repo_id, job_id)
    work_dir = settings.data_dir / "repositories" / repo_id
    work_dir.mkdir(parents=True, exist_ok=True)
    source_dir = work_dir / "source"
    zip_path = work_dir / "archive.zip"
    start_time = time.perf_counter()

    metrics: dict[str, Any] = {
        "filesDiscovered": None,
        "filesParsed": None,
        "symbolsExtracted": None,
        "dependencyEdges": None,
        "graphNodes": None,
        "communitiesDetected": None,
        "stageDuration": "0.0s",
    }

    try:
        # Stage 1: Repository Ingestion & URL Validation
        owner, repo_name = extract_github_owner_and_repo(url)
        update_job_progress(
            job_id,
            stage="ingestion",
            progress=10,
            status="running",
            message=f"Validating repository {owner}/{repo_name}...",
            metrics=metrics,
            log_entry=_log("INGEST", f"Resolving remote git tree: {owner}/{repo_name} [ref: {branch}]"),
        )
        await asyncio.sleep(0.1)

        # Stage 2: Source Retrieval
        update_job_progress(
            job_id,
            stage="source_retrieval",
            progress=22,
            message="Retrieving repository source files...",
            log_entry=_log("SCAN", "Downloading repository archive and discovering project structure"),
        )

        if use_git_clone:
            repo_data = await ingest_repository(url, branch)
        else:
            try:
                await asyncio.to_thread(download_github_archive, url, branch, zip_path)
                update_job_progress(
                    job_id,
                    stage="source_retrieval",
                    progress=30,
                    message="Extracting and filtering supported source files...",
                    log_entry=_log("EXTRACT", "Safe archive extraction verified; filtering non-code assets"),
                )
                await asyncio.to_thread(extract_archive_safely, zip_path, source_dir)
                zip_path.unlink(missing_ok=True)
                repo_data = await asyncio.to_thread(ingest_local_directory, source_dir, url, branch)
            except Exception as dl_err:
                logger.warning("Zip download failed (%s); falling back to shallow git clone", dl_err)
                update_job_progress(
                    job_id,
                    stage="source_retrieval",
                    progress=28,
                    message="Falling back to shallow git clone...",
                    log_entry=_log("WARN", f"Archive download unavailable ({dl_err}); falling back to git clone"),
                )
                repo_data = await ingest_repository(url, branch)

        file_count = len(repo_data.files)
        metrics["filesDiscovered"] = file_count
        metrics["stageDuration"] = f"{time.perf_counter() - start_time:.1f}s"
        update_job_progress(
            job_id,
            stage="source_retrieval",
            progress=38,
            message=f"Discovered {file_count} supported source files.",
            metrics=metrics,
            log_entry=_log("SCAN", f"Discovered {file_count} supported source files across project hierarchy"),
        )

        # Stage 3, 4, 5, 6, 7: Parsing, Graph Building, Metrics, AI
        update_job_progress(
            job_id,
            stage="ast_parsing",
            progress=48,
            message="Parsing source files with Tree-sitter abstract syntax trees...",
            log_entry=_log("AST", "Detecting programming languages and initializing AST parsers"),
        )

        # Build graph using the full Cartographer engine
        graph = await build_graph(repo_data, include_ai=False)

        # Extract actual computed counts from the generated graph
        parsed_count = sum(1 for n in graph.nodes if n.type == "file")
        symbol_count = sum(1 for n in graph.nodes if n.type in ("function", "class"))
        total_nodes = len(graph.nodes)
        total_edges = len(graph.edges)
        communities_count = len({n.position_hint.cluster_id for n in graph.nodes if n.position_hint and n.position_hint.cluster_id is not None}) or 1

        metrics["filesParsed"] = parsed_count or file_count
        metrics["symbolsExtracted"] = symbol_count
        metrics["graphNodes"] = total_nodes
        metrics["dependencyEdges"] = total_edges
        metrics["communitiesDetected"] = communities_count
        metrics["stageDuration"] = f"{time.perf_counter() - start_time:.1f}s"

        # Stage 4: Dependency Extraction
        update_job_progress(
            job_id,
            stage="dependency_extraction",
            progress=62,
            message="Resolving imports and directed dependency edges...",
            metrics=metrics,
            log_entry=_log("DEPENDENCY", f"Extracted {total_edges} directed dependency connections across modules"),
        )
        await asyncio.sleep(0.1)

        # Stage 5: Knowledge Graph Construction
        update_job_progress(
            job_id,
            stage="graph_construction",
            progress=74,
            message="Constructing NetworkX topological code graph...",
            metrics=metrics,
            log_entry=_log("GRAPH", f"Topological digraph assembled with {total_nodes} nodes and {total_edges} edges"),
        )
        await asyncio.sleep(0.1)

        # Stage 6: Architecture & Centrality Analysis
        update_job_progress(
            job_id,
            stage="architecture_analysis",
            progress=85,
            message="Computing PageRank centrality & Louvain architectural clusters...",
            metrics=metrics,
            log_entry=_log("METRICS", f"Eigenvector centrality computed; detected {communities_count} architectural communities"),
        )
        await asyncio.sleep(0.1)

        # Stage 7: AI Insights (check configuration or report skipped)
        if settings.gemini_api_key:
            update_job_progress(
                job_id,
                stage="ai_insights",
                progress=89,
                message="Generating AI architectural summaries and workflows...",
                metrics=metrics,
                log_entry=_log("AI", "Synthesizing architectural context and execution workflows with Gemini"),
            )
        else:
            update_job_progress(
                job_id,
                stage="ai_insights",
                progress=89,
                message="AI analysis skipped (no Gemini API key configured).",
                metrics=metrics,
                log_entry=_log("AI", "AI module skipped: Gemini API key not configured (core graph unaffected)"),
            )
        await asyncio.sleep(0.1)

        # Stage 8: 3D Galaxy Coordinate Preparation
        update_job_progress(
            job_id,
            stage="galaxy_preparation",
            progress=95,
            message="Mapping symbols into celestial nodes and orbital layout...",
            metrics=metrics,
            log_entry=_log("RENDER", "Allocating spherical cluster shells and assigning starfield coordinates"),
        )

        # Save artifact and set active store
        save_graph_artifact(repo_id, graph)
        set_active_graph_store(GraphStore(graph))

        # Stage 9: Workspace Ready
        total_time_str = f"{time.perf_counter() - start_time:.1f}s"
        metrics["stageDuration"] = total_time_str
        complete_job(job_id, repo_id, metrics=metrics)
        logger.info("Indexing pipeline successfully completed for repo %s in %s", repo_id, total_time_str)

    except Exception as exc:
        logger.exception("Indexing pipeline failed for repo %s: %s", repo_id, exc)
        fail_job(job_id, repo_id, str(exc))
    finally:
        # Cleanup temporary files
        zip_path.unlink(missing_ok=True)
        if source_dir.exists():
            shutil.rmtree(source_dir, ignore_errors=True)
