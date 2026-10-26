"""Workflow selection and validation."""

VALID_WORKFLOWS = {"auto", "text2image", "image2image"}


def select_workflow(
    requested_workflow: str | None,
    input_image: str | None,
) -> str:
    """Choose the generation workflow from user intent and available assets."""
    workflow = (requested_workflow or "auto").strip()
    if workflow not in VALID_WORKFLOWS:
        raise ValueError(f"Unsupported workflow: {workflow}")
    if workflow != "auto":
        return workflow
    if input_image:
        return "image2image"
    return "text2image"
