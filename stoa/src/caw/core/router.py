"""Provider routing for orchestration requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.errors import ProviderError

if TYPE_CHECKING:
    from caw.core.config import CAWConfig
    from caw.protocols.registry import ProviderRegistry


@dataclass
class ProviderSelection:
    provider_key: str
    model: str
    rationale: str
    fallback_chain: list[str]


class Router:
    """Selects model providers based on request and configuration."""

    def __init__(self, config: CAWConfig, registry: ProviderRegistry) -> None:
        self._config = config
        self._registry = registry

    async def route(
        self,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
        skill_preference: str | None = None,
    ) -> ProviderSelection:
        """Select a provider based on explicit, skill, or config defaults."""
        available = self._registry.list_providers()

        chosen_provider = explicit_provider
        rationale = "explicit provider from request"

        if chosen_provider is None and skill_preference is not None:
            chosen_provider = skill_preference
            rationale = "skill-level provider preference"

        if chosen_provider is None:
            if not available:
                raise ProviderError(
                    message="No providers configured",
                    code="provider_none_configured",
                )
            chosen_provider = available[0]
            rationale = "default provider from config"

        if chosen_provider not in available:
            raise ProviderError(
                message=f"Unknown provider: {chosen_provider}",
                code="provider_unknown",
                details={"provider_key": chosen_provider},
            )

        provider_config = self._config.providers.get(chosen_provider)
        if provider_config is None:
            raise ProviderError(
                message=f"Missing provider config for: {chosen_provider}",
                code="provider_config_missing",
                details={"provider_key": chosen_provider},
            )

        chosen_model = explicit_model or provider_config.default_model
        fallback_chain = [
            key
            for key in self._config.routing.fallback_chain
            if key != chosen_provider and key in available
        ]

        return ProviderSelection(
            provider_key=chosen_provider,
            model=chosen_model,
            rationale=rationale,
            fallback_chain=fallback_chain,
        )
