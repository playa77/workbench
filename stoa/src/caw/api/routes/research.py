"""Research capability endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from caw.api.deps import AppServices, get_provider_registry, get_services
from caw.api.schemas import APIResponse
from caw.capabilities.research.export import ResearchExporter
from caw.capabilities.research.ingest import IngestPipeline, SourceInput
from caw.capabilities.research.retrieve import Retriever
from caw.capabilities.research.synthesize import Synthesizer
from caw.protocols.registry import ProviderRegistry
from caw.storage.repository import ArtifactRepository, SourceRepository

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class IngestRequest(BaseModel):
    session_id: str
    path: str


class RetrieveRequest(BaseModel):
    session_id: str
    query: str
    top_k: int = 10


class SynthesizeRequest(BaseModel):
    session_id: str
    query: str
    top_k: int = 10


class ExportRequest(BaseModel):
    session_id: str
    query: str
    format: str = "markdown"


@router.post("/ingest")
async def ingest_source(
    request: IngestRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, str]]:
    pipeline = IngestPipeline(
        SourceRepository(services.database), services.database, services.trace_collector
    )
    source = await pipeline.ingest(
        SourceInput(session_id=request.session_id, path=Path(request.path))
    )
    return APIResponse(data={"source_id": source.id, "content_hash": source.content_hash or ""})


@router.post("/retrieve")
async def retrieve_sources(
    request: RetrieveRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[list[dict[str, str | float]]]:
    retriever = Retriever(services.database, services.trace_collector)
    results = await retriever.retrieve(
        query=request.query, session_id=request.session_id, top_k=request.top_k
    )
    return APIResponse(
        data=[
            {
                "source_id": item.source_id,
                "chunk_id": item.chunk_id,
                "content": item.content,
                "relevance_score": item.relevance_score,
            }
            for item in results
        ]
    )


@router.post("/synthesize")
async def synthesize(
    request: SynthesizeRequest,
    services: Annotated[AppServices, Depends(get_services)],
    provider_registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> APIResponse[dict[str, object]]:
    retriever = Retriever(services.database, services.trace_collector)
    retrieval_results = await retriever.retrieve(
        query=request.query,
        session_id=request.session_id,
        top_k=request.top_k,
    )
    provider_key = provider_registry.list_providers()[0]
    provider = provider_registry.get(provider_key)
    synthesis_result = await Synthesizer(
        provider=provider,
        trace_collector=services.trace_collector,
        model="gpt-4o-mini",
    ).synthesize(
        query=request.query, retrieval_results=retrieval_results, session_id=request.session_id
    )
    return APIResponse(
        data={
            "query": synthesis_result.query,
            "claims": [
                {
                    "text": claim.text,
                    "citation_ids": claim.citation_ids,
                    "confidence": claim.confidence,
                }
                for claim in synthesis_result.claims
            ],
            "uncertainty_markers": synthesis_result.uncertainty_markers,
            "source_map": synthesis_result.source_map,
            "trace_id": synthesis_result.trace_id,
        }
    )


@router.post("/export")
async def export_report(
    request: ExportRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, str]]:
    retriever = Retriever(services.database, services.trace_collector)
    retrieval_results = await retriever.retrieve(
        query=request.query,
        session_id=request.session_id,
    )
    provider_key = services.provider_registry.list_providers()[0]
    provider = services.provider_registry.get(provider_key)
    synthesis_result = await Synthesizer(
        provider, services.trace_collector, model="gpt-4o-mini"
    ).synthesize(
        query=request.query,
        retrieval_results=retrieval_results,
        session_id=request.session_id,
    )
    exporter = ResearchExporter(
        artifact_repo=ArtifactRepository(services.database),
        artifact_dir=Path(services.config.storage.artifact_dir),
    )
    artifact = await exporter.export(
        synthesis_result, session_id=request.session_id, format=request.format
    )
    return APIResponse(data={"artifact_id": artifact.id, "path": artifact.path or ""})
