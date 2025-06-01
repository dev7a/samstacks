"""
Pydantic V2 models for defining the structure of the pipeline.yml manifest.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from pathlib import Path

# Type alias for the flexible SAM configuration content
SamConfigContentType = Dict[str, Any]

# Forward declaration for PipelineInputItem if it becomes a Pydantic model
# For now, defined_inputs in PipelineSettingsModel will use Dict[str, Any]


class StackModel(BaseModel):
    """
    Pydantic V2 model for a single stack definition within the pipeline.
    Corresponds to an item in the 'stacks' list in pipeline.yml.
    """

    id: str
    dir: Path  # Paths will be resolved relative to the manifest file
    name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = Field(default_factory=lambda: {})
    stack_name_suffix: Optional[str] = None
    region: Optional[str] = None
    profile: Optional[str] = None
    if_condition: Optional[str] = Field(default=None, alias="if")
    run_script: Optional[str] = Field(default=None, alias="run")

    # New field for SAM config overrides per stack
    # This will hold the content of 'sam_config_overrides' from pipeline.yml
    sam_config_overrides: Optional[SamConfigContentType] = Field(default=None)

    # Pydantic V2 configuration
    model_config = {
        "populate_by_name": True,  # Allows using aliases like 'if' and 'run'
        "extra": "forbid",  # Forbid extra fields not defined in the model
    }

    # Resolve dir to an absolute path if manifest_base_dir is provided in context
    # This validator might be better placed at the PipelineManifestModel level
    # or handled during the instantiation of the runtime Stack object in core.py
    # For now, Pydantic will ensure it's a Path object.


class PipelineInputItem(BaseModel):
    """
    Pydantic V2 model for a single input definition within pipeline_settings.inputs.
    """

    type: str  # e.g., "string", "number", "boolean"
    description: Optional[str] = None
    default: Optional[Any] = None
    # 'required' is implicitly handled by Pydantic if 'default' is not set for an Optional field,
    # but SAMstacks logic explicitly checks for 'default' key absence.

    model_config = {"extra": "forbid"}

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        valid_types = {"string", "number", "boolean"}
        if v not in valid_types:
            raise ValueError(f"Input type must be one of {sorted(list(valid_types))}")
        return v


class PipelineSettingsModel(BaseModel):
    """
    Pydantic V2 model for the 'pipeline_settings' section of pipeline.yml.
    """

    stack_name_prefix: Optional[str] = None
    stack_name_suffix: Optional[str] = None
    default_region: Optional[str] = None
    default_profile: Optional[str] = None
    inputs: Optional[Dict[str, PipelineInputItem]] = Field(default_factory=lambda: {})

    # New field for default SAM config at the pipeline level
    # This will hold the content of 'default_sam_config' from pipeline.yml
    default_sam_config: Optional[SamConfigContentType] = Field(default=None)

    model_config = {"extra": "forbid"}


class PipelineManifestModel(BaseModel):
    """
    Root Pydantic V2 model for the entire pipeline.yml manifest file.
    """

    pipeline_name: str
    pipeline_description: Optional[str] = None
    # Use Field(default_factory=...) for mutable defaults like dict or list
    pipeline_settings: PipelineSettingsModel = Field(
        default_factory=PipelineSettingsModel
    )
    stacks: List[StackModel] = Field(default_factory=lambda: [])

    # Potentially, custom root model validation could go here if needed
    # e.g., @model_validator(mode='before') or @model_validator(mode='after')
    # For now, detailed validation logic is in ManifestValidator and core.py

    model_config = {"extra": "forbid"}

    @field_validator("stacks")
    @classmethod
    def stack_ids_must_be_unique(cls, v: List[StackModel]) -> List[StackModel]:
        seen_ids = set()
        for stack in v:
            if stack.id in seen_ids:
                raise ValueError(f"Duplicate stack ID found: {stack.id}")
            seen_ids.add(stack.id)
        return v


# Example of how to parse in V2:
# from pathlib import Path
# import yaml
# from pydantic import ValidationError
# manifest_path = Path("path/to/your/pipeline.yml")
# with open(manifest_path, 'r') as f:
#     data = yaml.safe_load(f)
# try:
#     pipeline_obj = PipelineManifestModel.model_validate(data)
#     print(pipeline_obj.pipeline_settings.default_sam_config)
#     if pipeline_obj.stacks:
#         print(pipeline_obj.stacks[0].sam_config_overrides)
# except ValidationError as e:
#     print(e)
