"""FastAPI views for core routes."""

from fastapi import APIRouter

from workbench.__version__ import __version__

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": __version__}
