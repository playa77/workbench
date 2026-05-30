"""Provider factory — maps provider names to implementations."""

from __future__ import annotations

from presearch.config import PResearchConfig
from presearch.providers.base import ProviderInterface

PROVIDER_REGISTRY: dict[str, str] = {
    "custom": "presearch.providers.custom.provider.CustomProvider",
}


def get_provider(config: PResearchConfig) -> ProviderInterface:
    """Instantiate the configured provider."""
    name = config.provider.lower()
    if name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Available: {', '.join(PROVIDER_REGISTRY)}"
        )
    import importlib

    module_path = PROVIDER_REGISTRY[name]
    mod_path, cls_name = module_path.rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls(config)
