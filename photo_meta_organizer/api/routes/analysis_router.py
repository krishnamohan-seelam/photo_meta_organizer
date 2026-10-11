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
from photo_meta_organizer.application.job_work import analyze_work
from photo_meta_organizer.application.jobs import JobContext, JobOutcome, Work
from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
    AnalyzePhotosUseCase,
)
from photo_meta_organizer.application.use_cases.resolve_ai_tags_use_case import (
    ResolveAiTagsUseCase,
)
from photo_meta_organizer.application.use_cases.semantic_search_use_case import (
    AnalysisNotReadyError,
    SemanticSearchUseCase,
)
from photo_meta_organizer.domain.analysis import AiTagStatus
from photo_meta_organizer.infrastructure.analysis.model_store import (
    DownloadCancelled,
    ModelStore,
    ModelUnavailableError,
)
from photo_meta_organizer.infrastructure.analysis.runtime import ai_runtime_installed

analysis_router = APIRouter(prefix="/api", tags=["ai"])
ai_tags_router = APIRouter(prefix="/api/ai-tags", tags=["ai"])

_AI_JOB_KINDS = ("model-download", "analyze")
_RUNTIME_HINT = (
    "The AI features need the optional 'ai' extra (onnxruntime and tokenizers): "
    "`uv sync --extra ai`, or `pip install photo-meta-organizer[ai]`."
)


def _job_folder(services: Services) -> str:
    """One shared pseudo-folder, so a download and an analysis exclude each other."""
    return str(services.settings.models_dir)


def _require_runtime() -> None:
    if not ai_runtime_installed():
        raise HTTPException(status_code=503, detail=_RUNTIME_HINT)


def _require_model(services: Services) -> None:
    if not services.model_store.is_installed():
        raise HTTPException(
            status_code=409,
            detail="The AI model is not installed yet. Download it first "
            "(POST /api/analysis/model/download).",
        )


def _download_work(store: ModelStore) -> Work:
    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(done: int, total: int) -> None:
            ctx.report_progress(total=total, processed=done, failed=0)

        try:
            store.download(progress=on_progress, should_cancel=ctx.cancel_requested)
        except DownloadCancelled:
            return JobOutcome(
                message="Download cancelled; nothing partial was kept.", cancelled=True
            )
        return JobOutcome(
            message=f"Installed the model ({store.manifest.total_bytes / 1e6:.0f} MB).",
            counts={"bytes": store.manifest.total_bytes},
        )

    return work


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
        runtime_installed=ai_runtime_installed(),
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
    if services.model_store.is_installed():
        raise HTTPException(status_code=409, detail="The model is already installed.")
    return _submit(
        services.jobs, "model-download", _job_folder(services), _download_work(services.model_store)
    )


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
    _require_runtime()
    _require_model(services)
    use_case = AnalyzePhotosUseCase(
        services.analysis, services.embedder, services.tagger if request.tags else None
    )
    work = analyze_work(use_case, reanalyze=request.reanalyze, limit=request.limit)
    return _submit(services.jobs, "analyze", _job_folder(services), work)


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
    _require_runtime()
    _require_model(services)
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
