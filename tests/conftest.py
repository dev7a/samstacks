import pytest
from pathlib import Path
from unittest import mock  # For mocker argument in create_mock_template_processor
from samstacks.templating import (
    TemplateProcessor,
)  # For spec in create_mock_template_processor


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Creates a temporary project directory for tests that need file system operations."""
    project_dir = tmp_path / "test_project_root"  # tmp_path is a pytest fixture itself
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


@pytest.fixture
def create_mock_template_processor(mocker) -> mock.MagicMock:
    """Creates a mock TemplateProcessor instance."""
    mock_tp = mocker.MagicMock(spec=TemplateProcessor)
    mock_tp.process_structure.side_effect = (
        lambda data_structure, **kwargs: data_structure
    )
    mock_tp.process_string.side_effect = (
        lambda template_string, **kwargs: template_string if template_string else ""
    )
    return mock_tp
