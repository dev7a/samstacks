"""
Custom exceptions for the samstacks package.
"""


class SamStacksError(Exception):
    """Base exception for all samstacks errors."""

    pass


class ManifestError(SamStacksError):
    """Raised when there's an error parsing or validating the manifest file."""

    pass


class TemplateError(SamStacksError):
    """Raised when there's an error processing template substitutions."""

    pass


class StackDeploymentError(SamStacksError):
    """Raised when a stack deployment fails."""

    pass


class PostDeploymentScriptError(SamStacksError):
    """Raised when a post-deployment script fails."""

    pass


class OutputRetrievalError(SamStacksError):
    """Raised when retrieving stack outputs fails."""

    pass


class ConditionalEvaluationError(SamStacksError):
    """Raised when evaluating an 'if' condition fails."""

    pass


class StackDeletionError(SamStacksError):
    """Error during CloudFormation stack deletion."""

    pass
