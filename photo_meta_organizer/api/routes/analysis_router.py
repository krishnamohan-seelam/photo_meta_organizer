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

from fastapi import APIRouter, Depends, HTTPException, Query

from photo_meta_organizer.api.dependencies import Services, get_services
from photo_meta_organizer.api.job_factory import require_model, require_runtime, work_for
from photo_meta_organizer.api.routes.photos_router import (
    _search_query,
    _submit,
    _to_response,
)
from photo_meta_organizer.api.schemas import (
    AiTagBatchRequest,
    AiTagBatchResponse,
    AiTagSchema,
    AnalysisStatusResponse,
    AnalyzeRequest,
    FacetCountSchema,
    JobResponse,
    ModelDownloadRequest,
    ResolveAiTagRequest,
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
    return SemanticSearchResponse(
        items=[SemanticHitSchema(photo=_to_response(h.photo), score=h.score) for h in hits],
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
