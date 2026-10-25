"""AI analysis routes (Phase 5, ADR-002).

    GET   /api/analysis/status           - Is the runtime/model there, how far along is analysis
    POST  /api/analysis/model/download   - Download the model (needs explicit consent), as a job
    POST  /api/analysis/run              - Analyze the library (embeddings + tags), as a job
    POST  /api/search/semantic           - Find photos by meaning, or "like this one"
    GET   /api/photos/{hash}/ai-tags     - A photo's suggested tags
    POST  /api/photos/{hash}/ai-tags     - Accept / reject / reopen one suggestion
    GET   /api/ai-tags                   - How many photos carry each suggested label
    POST  /api/ai-tags/batch             - Accept / reject suggestions across a selection

Long work (the download, the analysis) runs as a job like index and sync, so progress, cancel
and per-file errors come from ``/api/jobs``. Both share one job "folder" (the models directory)
so they cannot run at once. A suggestion becomes a label only when accepted.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query

from photo_meta_organizer.api.dependencies import Services, get_services
from photo_meta_organizer.api.job_factory import require_model, require_runtime, work_for
from photo_meta_organizer.api.routes.photos_router import (
    _search_query,
    _submit,
    to_responses,
)
from photo_meta_organizer.api.schemas import (
    AcceptAboveRequest,
    AiTagBatchRequest,
    AiTagBatchResponse,
    AiTagSchema,
    AnalysisStatusResponse,
    AnalyzeRequest,
    FacetCountSchema,
    JobResponse,
    ModelDownloadRequest,
    ResolveAiTagRequest,
    ReviewCountResponse,
    ReviewItemSchema,
    ReviewItemsResponse,
    ReviewLabelSchema,
    SemanticHitSchema,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from photo_meta_organizer.application.use_cases.resolve_ai_tags_use_case import (
    ResolveAiTagsUseCase,
)
from photo_meta_organizer.application.use_cases.semantic_search_use_case import (
    AnalysisNotReadyError,
    SemanticSearchUseCase,
)
from photo_meta_organizer.domain.analysis import AiTagStatus
from photo_meta_organizer.infrastructure.analysis import runtime
from photo_meta_organizer.infrastructure.analysis.model_store import ModelUnavailableError

analysis_router = APIRouter(prefix="/api", tags=["ai"])
ai_tags_router = APIRouter(prefix="/api/ai-tags", tags=["ai"])

_AI_JOB_KINDS = ("model-download", "analyze")


def _job_folder(services: Services) -> str:
    """One shared pseudo-folder, so a download and an analysis exclude each other."""
    return str(services.settings.models_dir)


@analysis_router.get(
    "/analysis/status",
    response_model=AnalysisStatusResponse,
    summary="What the AI features need and how far along analysis is",
)
def analysis_status(services: Services = Depends(get_services)) -> AnalysisStatusResponse:
    store = services.model_store
    model_id = services.embedder.model_id
    total = services.repository.count()
    analyzed = services.analysis.count_embeddings(model_id)
    active = next(
        (j for j in services.jobs.list() if j.kind in _AI_JOB_KINDS and not j.status.is_terminal),
        None,
    )
    return AnalysisStatusResponse(
        runtime_installed=runtime.ai_runtime_installed(),
        model_installed=store.is_installed(),
        model_id=store.manifest.model_id,
        model_source=store.manifest.source,
        model_licence=store.manifest.licence,
        download_bytes=store.missing_bytes(),
        total_photos=total,
        analyzed_photos=analyzed,
        pending_photos=max(0, total - analyzed),
        active_job_id=active.id if active else None,
        active_job_kind=active.kind if active else None,
    )


@analysis_router.post(
    "/analysis/model/download",
    response_model=JobResponse,
    status_code=202,
    summary="Download the AI model (needs explicit consent)",
)
def download_model(
    request: ModelDownloadRequest, services: Services = Depends(get_services)
) -> JobResponse:
    """Start the one-time model download as a job (progress is in bytes).

    The body must say ``{"accept": true}``: the UI sends it only after telling the user what is
    fetched (size, source, licence). Only the model is downloaded; no photo data is sent.
    """
    folder = _job_folder(services)
    work = work_for("model-download", folder, {}, services)
    return _submit(services.jobs, "model-download", folder, work, {})


@analysis_router.post(
    "/analysis/run",
    response_model=JobResponse,
    status_code=202,
    summary="Analyze the library: embeddings and suggested tags",
)
def run_analysis(
    request: AnalyzeRequest, services: Services = Depends(get_services)
) -> JobResponse:
    """Analyze every photo that has no embedding from the current model, as a job.

    Incremental and safe to repeat. ``reanalyze`` redoes everything; ``limit`` caps one run.
    Refused with 503 without the ``ai`` extra and 409 without the model or while another AI job
    runs. Suggestions never change the user's labels until accepted.
    """
    folder = _job_folder(services)
    params = request.model_dump()
    return _submit(
        services.jobs, "analyze", folder, work_for("analyze", folder, params, services), params
    )


@analysis_router.post(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    summary="Find photos by meaning, or like another photo",
)
def semantic_search(
    request: SemanticSearchRequest, services: Services = Depends(get_services)
) -> SemanticSearchResponse:
    """Rank analysed photos by similarity to ``text`` (or to the photo ``like_hash``).

    The usual search filters apply and decide who competes. Returns the ``k`` best matches,
    best first. 409 if nothing (or that photo) has been analysed yet.
    """
    require_runtime()
    require_model(services)
    use_case = SemanticSearchUseCase(services.analysis, services.embedder, services.repository)
    query = _search_query(request)
    try:
        if request.like_hash is not None:
            hits = use_case.similar_to(request.like_hash, query=query, k=request.k)
        else:
            hits = use_case.by_text(request.text or "", query=query, k=request.k)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Photo '{request.like_hash}' not found."
        ) from None
    except AnalysisNotReadyError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ModelUnavailableError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    photos = to_responses([h.photo for h in hits], services.repository)
    return SemanticSearchResponse(
        items=[
            SemanticHitSchema(photo=p, score=h.score) for p, h in zip(photos, hits, strict=True)
        ],
        model_id=services.embedder.model_id,
    )


def _tag_schemas(services: Services, file_hash: str) -> list[AiTagSchema]:
    return [
        AiTagSchema(
            label=t.label, confidence=t.confidence, model_id=t.model_id, status=t.status.value
        )
        for t in services.analysis.list_ai_tags(file_hash)
    ]


def _require_photo(services: Services, file_hash: str) -> None:
    if services.repository.get_by_filehash(file_hash) is None:
        raise HTTPException(status_code=404, detail=f"Photo '{file_hash}' not found.")


@analysis_router.get(
    "/photos/{file_hash}/ai-tags",
    response_model=list[AiTagSchema],
    summary="A photo's AI tag suggestions",
)
def list_photo_ai_tags(
    file_hash: str, services: Services = Depends(get_services)
) -> list[AiTagSchema]:
    """Every suggestion for the photo in any status, most confident first."""
    _require_photo(services, file_hash)
    return _tag_schemas(services, file_hash)


@analysis_router.post(
    "/photos/{file_hash}/ai-tags",
    response_model=list[AiTagSchema],
    summary="Accept, reject or reopen one suggestion",
)
def resolve_photo_ai_tag(
    file_hash: str, request: ResolveAiTagRequest, services: Services = Depends(get_services)
) -> list[AiTagSchema]:
    """``accept`` adds the label to the photo (an ordinary label from then on); ``reject`` keeps
    it from being suggested again; ``reset`` reopens a decided suggestion. None removes a label."""
    _require_photo(services, file_hash)
    use_case = ResolveAiTagsUseCase(services.analysis, services.repository)
    if not use_case.resolve(file_hash, request.label, request.action):
        raise HTTPException(status_code=404, detail=f"Photo has no suggestion '{request.label}'.")
    return _tag_schemas(services, file_hash)


@ai_tags_router.get(
    "", response_model=list[FacetCountSchema], summary="Suggested labels and their photo counts"
)
def ai_tag_counts(
    status: AiTagStatus = Query(default=AiTagStatus.SUGGESTED),
    services: Services = Depends(get_services),
) -> list[FacetCountSchema]:
    """Each label and how many photos carry it in ``status``, most common first."""
    return [FacetCountSchema(name=n, count=c) for n, c in services.analysis.ai_tag_counts(status)]


@ai_tags_router.get(
    "/review",
    response_model=list[ReviewLabelSchema],
    summary="Labels with open suggestions, most confident first",
)
def review_labels(services: Services = Depends(get_services)) -> list[ReviewLabelSchema]:
    """The review queue's groups: each label that still has open suggestions, with how many
    photos and the confidence of its best one. The label with the most confident suggestion
    comes first."""
    return [
        ReviewLabelSchema(label=r.label, count=r.count, top_confidence=r.top_confidence)
        for r in services.analysis.review_labels()
    ]


@ai_tags_router.get(
    "/review/items",
    response_model=ReviewItemsResponse,
    summary="Open suggestions of one label, most confident first",
)
def review_items(
    label: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    min_confidence: float = Query(default=0.0, ge=0, le=1),
    services: Services = Depends(get_services),
) -> ReviewItemsResponse:
    """One page of the photos with an open suggestion of ``label``, best first. 404 for a
    label with none (it may have been fully reviewed meanwhile)."""
    total = services.analysis.count_open(label, min_confidence)
    if total == 0 and services.analysis.count_open(label) == 0:
        raise HTTPException(status_code=404, detail=f"No open suggestions of '{label}'.")
    items = services.analysis.review_items(label, limit, offset, min_confidence)
    files = services.repository.files_of([i.file_hash for i in items])
    return ReviewItemsResponse(
        label=label,
        total=total,
        items=[
            ReviewItemSchema(
                file_hash=i.file_hash,
                name=os.path.basename(files[i.file_hash][0].path) if i.file_hash in files else "",
                confidence=i.confidence,
            )
            for i in items
        ],
    )


@ai_tags_router.get(
    "/review/count",
    response_model=ReviewCountResponse,
    summary="How many open suggestions of a label reach a confidence",
)
def review_count(
    label: str,
    min_confidence: float = Query(default=0.0, ge=0, le=1),
    services: Services = Depends(get_services),
) -> ReviewCountResponse:
    """What ``POST /api/ai-tags/accept-above`` would accept: show it before applying."""
    return ReviewCountResponse(count=services.analysis.count_open(label, min_confidence))


@ai_tags_router.post(
    "/accept-above",
    response_model=AiTagBatchResponse,
    summary="Accept every open suggestion of a label above a confidence",
)
def accept_above(
    request: AcceptAboveRequest, services: Services = Depends(get_services)
) -> AiTagBatchResponse:
    """Accept the label on every photo whose open suggestion is at or above
    ``min_confidence``. Ask ``GET /api/ai-tags/review/count`` first and show the user the count."""
    result = ResolveAiTagsUseCase(services.analysis, services.repository).accept_above(
        request.label, request.min_confidence
    )
    return AiTagBatchResponse(
        photos_changed=result.photos_changed, tags_changed=result.tags_changed
    )


@ai_tags_router.post(
    "/batch",
    response_model=AiTagBatchResponse,
    summary="Accept or reject suggestions across many photos",
)
def resolve_ai_tags_batch(
    request: AiTagBatchRequest, services: Services = Depends(get_services)
) -> AiTagBatchResponse:
    """Without ``labels`` this takes every open suggestion of the selected photos; with them,
    exactly those labels. Unknown photos are skipped."""
    result = ResolveAiTagsUseCase(services.analysis, services.repository).resolve_many(
        request.photo_hashes, request.labels, request.action
    )
    return AiTagBatchResponse(
        photos_changed=result.photos_changed, tags_changed=result.tags_changed
    )
