def strip_id(doc: dict) -> dict:
    """Remove MongoDB's internal _id before mapping a document to a schema."""
    doc.pop("_id", None)
    return doc
