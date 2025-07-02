"""
Pydantic V2 models for defining the structure of the pipeline.yml manifest.
"""

from typing import Any, Dict, List, Optional, TypedDict
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
    config: Optional[Path] = Field(
        default=None, description="Path to external SAM configuration file to generate"
    )
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

    @field_validator("config", mode="before")
    @classmethod
    def validate_config_path(cls, v: Any) -> Optional[Path]:
        """
        Validate and normalize external config paths.

        Rules:
        - Ends with .yaml/.yml: Use literal path
        - Ends with /: Append 'samconfig.yaml'
        - Anything else: Validation error
        """
        if v is None:
            return v

        # Work with the original string input before Path conversion
        config_str = str(v)

        # Rule 1: Explicit file paths (.yaml/.yml)
        if config_str.endswith((".yaml", ".yml")):
            return Path(config_str)

        # Rule 2: Directory paths (ends with /)
        if config_str.endswith("/"):
            return Path(config_str + "samconfig.yaml")

        # Rule 3: Invalid format - must end with / or .yaml/.yml
        raise ValueError(
            f"Invalid config path '{config_str}'. "
            f"Config path must end with '/' (directory) or '.yaml'/'.yml' (file). "
            f"Examples: 'configs/dev/app/' or 'configs/dev/app/samconfig.yaml'"
        )

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


class OutputMaskingCategoriesModel(BaseModel):
    """Configuration for different categories of output masking."""

    account_ids: bool = Field(
        default=False, description="Mask AWS account IDs (12-digit numbers) in outputs"
    )

    api_endpoints: bool = Field(
        default=False,
        description="Mask API Gateway URLs, Lambda Function URLs, and similar API endpoints",
    )

    database_endpoints: bool = Field(
        default=False,
        description="Mask RDS, ElastiCache, DocumentDB, and other database connection endpoints",
    )

    load_balancer_dns: bool = Field(
        default=False,
        description="Mask Application Load Balancer, Network Load Balancer, and Classic Load Balancer DNS names",
    )

    cloudfront_domains: bool = Field(
        default=False, description="Mask CloudFront distribution domain names"
    )

    s3_bucket_domains: bool = Field(
        default=False,
        description="Mask S3 bucket website endpoints and transfer acceleration endpoints",
    )

    ip_addresses: bool = Field(
        default=False, description="Mask IPv4 and IPv6 addresses"
    )


class CustomMaskingPatternModel(BaseModel):
    """Configuration for custom masking patterns."""

    pattern: str = Field(description="Regular expression pattern to match")

    replacement: str = Field(
        default="***", description="Replacement string for matched patterns"
    )

    description: Optional[str] = Field(
        default=None, description="Optional description of what this pattern masks"
    )


class OutputMaskingModel(BaseModel):
    """Comprehensive output masking configuration."""

    enabled: bool = Field(
        default=False,
        description="Enable output masking (must be true for any masking to occur)",
    )

    categories: OutputMaskingCategoriesModel = Field(
        default_factory=OutputMaskingCategoriesModel,
        description="Predefined masking categories",
    )

    custom_patterns: List[CustomMaskingPatternModel] = Field(
        default_factory=list, description="Custom regex patterns for advanced masking"
    )


class PipelineSettingsModel(BaseModel):
    """
    Pydantic V2 model for the 'pipeline_settings' section of pipeline.yml.
    """

    stack_name_prefix: Optional[str] = None
    stack_name_suffix: Optional[str] = None
    default_region: Optional[str] = None
    default_profile: Optional[str] = None
    inputs: Optional[Dict[str, PipelineInputItem]] = Field(default_factory=lambda: {})

    # Comprehensive masking configuration
    output_masking: OutputMaskingModel = Field(
        default_factory=OutputMaskingModel,
        description="Comprehensive output masking configuration for security",
    )

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
    summary: Optional[str] = None

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


class StackReportItem(TypedDict):
    stack_id_from_pipeline: str
    deployed_stack_name: str
    cfn_status: Optional[str]
    parameters: Dict[str, str]
    outputs: Dict[str, str]


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
