"""Application layer containing use cases and interfaces.

This layer orchestrates the application logic and defines interfaces that
the infrastructure layer must implement. Uses dependency injection for flexibility.
"""

from photo_meta_organizer.application.orchestrators import ExtractorOrchestrator

__all__ = ["ExtractorOrchestrator"]
