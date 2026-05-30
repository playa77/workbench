"""Research capability pillar."""

from caw.capabilities.research.export import ResearchExporter
from caw.capabilities.research.ingest import IngestPipeline, SourceInput
from caw.capabilities.research.retrieve import RetrievalResult, Retriever
from caw.capabilities.research.synthesize import SynthesisResult, SynthesizedClaim, Synthesizer

__all__ = [
    "IngestPipeline",
    "ResearchExporter",
    "RetrievalResult",
    "Retriever",
    "SourceInput",
    "SynthesisResult",
    "SynthesizedClaim",
    "Synthesizer",
]
