"""Skill and provider discovery endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from caw.api.deps import get_provider_registry, get_skill_registry
from caw.api.schemas import APIResponse, ProviderHealthResponse
from caw.protocols.registry import ProviderRegistry
from caw.skills.registry import SkillRegistry

router = APIRouter(prefix="/api/v1", tags=["skills", "providers"])


@router.get("/skills")
async def list_skills(
    skill_registry: Annotated[SkillRegistry, Depends(get_skill_registry)],
) -> APIResponse[list[dict[str, object]]]:
    return APIResponse(
        data=[
            {
                "id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "provider_preference": skill.provider_preference,
            }
            for skill in skill_registry.list_skills()
        ]
    )


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    skill_registry: Annotated[SkillRegistry, Depends(get_skill_registry)],
) -> APIResponse[dict[str, object] | None]:
    skill = skill_registry.get_skill(skill_id)
    if skill is None:
        return APIResponse(status="error", error_code="skill_not_found", message="Skill not found")
    return APIResponse(
        data={
            "id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "provider_preference": skill.provider_preference,
            "body": skill.body,
        }
    )


@router.get("/skills/packs")
async def list_packs(
    skill_registry: Annotated[SkillRegistry, Depends(get_skill_registry)],
) -> APIResponse[list[dict[str, object]]]:
    return APIResponse(
        data=[
            {
                "id": pack.pack_id,
                "name": pack.name,
                "description": pack.description,
                "version": pack.version,
                "skills": pack.skills,
            }
            for pack in skill_registry.list_packs()
        ]
    )


@router.get("/providers")
async def list_providers(
    provider_registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> APIResponse[list[str]]:
    return APIResponse(data=provider_registry.list_providers())


@router.get("/providers/{provider_id}/health")
async def provider_health(
    provider_id: str,
    provider_registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> APIResponse[ProviderHealthResponse]:
    provider = provider_registry.get(provider_id)
    health = await provider.health_check()
    return APIResponse(
        data=ProviderHealthResponse(
            provider=provider_id,
            available=health.available,
            latency_ms=health.latency_ms,
            error=health.error,
        )
    )
