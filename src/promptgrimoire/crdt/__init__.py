"""CRDT synchronization module for real-time collaboration."""

from promptgrimoire.crdt.annotation_doc import (
    AnnotationDocument,
    AnnotationDocumentRegistry,
)
from promptgrimoire.crdt.sync import SharedDocument

__all__ = ["AnnotationDocument", "AnnotationDocumentRegistry", "SharedDocument"]
