"""
Comprehensive tests for complex template expression evaluation.

Tests the simplified templating approach that uses simpleeval for
complex mathematical, logical, and fallback expressions.
"""

import os
import pytest
from samstacks.templating import TemplateProcessor
from samstacks.exceptions import TemplateError


class TestComplexExpressions:
    """Test complex mathematical and logical expressions."""

    def setup_method(self):
        """Set up test environment."""
        self.defined_inputs = {
            "environment": {"type": "string", "default": "dev"},
            "count": {"type": "number", "default": 100},
            "enabled": {"type": "boolean", "default": True},
            "ratio": {"type": "number", "default": 0.5},
            "name": {"type": "string", "default": "test-app"},
        }
        self.processor = TemplateProcessor(
            defined_inputs=self.defined_inputs, cli_inputs={}
        )
        self.processor.add_stack_outputs("db", {"ConnectionString": "db://localhost"})

    def test_complex_ternary_expressions(self):
        """Test complex ternary-like expressions with multiple conditions."""
        # Classic ternary pattern
        result = self.processor.process_string(
            "${{ inputs.count < 50 && 'small' || inputs.count < 200 && 'medium' || 'large' }}"
        )
        assert result == "medium"  # 100 is between 50 and 200

        # With different operators
        result = self.processor.process_string(
            "${{ inputs.environment == 'prod' && 1000 || inputs.environment == 'staging' && 500 || 100 }}"
        )
        assert result == "100"  # environment is 'dev'

    def test_mathematical_expressions(self):
        """Test complex mathematical operations."""
        # Basic arithmetic with precedence
        result = self.processor.process_string("${{ inputs.count * 2 + 10 }}")
        assert result == "210"  # (100 * 2) + 10

        # With parentheses
        result = self.processor.process_string("${{ (inputs.count + 10) * 2 }}")
        assert result == "220"  # (100 + 10) * 2

        # Division and modulo
        result = self.processor.process_string("${{ inputs.count / 4 }}")
        assert result == "25.0"  # Python division returns float

        result = self.processor.process_string("${{ inputs.count % 30 }}")
        assert result == "10"  # 100 % 30

        # Power operations
        result = self.processor.process_string("${{ 2 ** 3 }}")
        assert result == "8"

    def test_comparison_operators(self):
        """Test all comparison operators."""
        test_cases = [
            ("inputs.count == 100", "true"),
            ("inputs.count != 100", "false"),
            ("inputs.count > 50", "true"),
            ("inputs.count < 50", "false"),
            ("inputs.count >= 100", "true"),
            ("inputs.count <= 100", "true"),
            ("inputs.count >= 101", "false"),
            ("inputs.environment == 'dev'", "true"),
            ("inputs.environment != 'prod'", "true"),
        ]

        for expr, expected in test_cases:
            result = self.processor.process_string(f"${{{{ {expr} }}}}")
            assert result == expected, (
                f"Expression {expr} should evaluate to {expected}, got {result}"
            )

    def test_boolean_logic(self):
        """Test complex boolean logic expressions."""
        # AND logic
        result = self.processor.process_string(
            "${{ inputs.enabled && inputs.count > 50 }}"
        )
        assert result == "true"

        # OR logic
        result = self.processor.process_string(
            "${{ inputs.environment == 'prod' || inputs.count > 50 }}"
        )
        assert result == "true"  # Second condition is true

        # NOT logic
        result = self.processor.process_string("${{ !inputs.enabled }}")
        assert result == "false"

        # Complex combinations
        result = self.processor.process_string(
            "${{ (inputs.enabled && inputs.count > 200) || (inputs.environment == 'dev' && inputs.count < 200) }}"
        )
        assert result == "true"  # Second part is true

    def test_function_calls(self):
        """Test function calls in expressions."""
        # Type conversion functions
        result = self.processor.process_string("${{ int(inputs.ratio * 100) }}")
        assert result == "50"  # int(0.5 * 100)

        result = self.processor.process_string("${{ str(inputs.count) }}")
        assert result == "100"

        result = self.processor.process_string("${{ float(inputs.count) }}")
        assert result == "100.0"

        # Nested function calls
        result = self.processor.process_string("${{ int(float(inputs.count) / 3) }}")
        assert result == "33"  # int(100.0 / 3)

    def test_fallback_expressions(self):
        """Test various fallback patterns."""
        # Environment variable fallbacks
        result = self.processor.process_string("${{ env.MISSING || 'default' }}")
        assert result == "default"

        # Input fallbacks
        result = self.processor.process_string("${{ inputs.missing || inputs.count }}")
        assert result == "100"

        # Stack output fallbacks
        result = self.processor.process_string(
            "${{ stacks.missing.outputs.Value || stacks.db.outputs.ConnectionString }}"
        )
        assert result == "db://localhost"

        # Chained fallbacks
        result = self.processor.process_string(
            "${{ env.FIRST || env.SECOND || 'final_default' }}"
        )
        assert result == "final_default"

    def test_mixed_type_expressions(self):
        """Test expressions mixing different data types."""
        # String concatenation patterns
        result = self.processor.process_string(
            "${{ inputs.enabled && inputs.name + '-enabled' || inputs.name + '-disabled' }}"
        )
        assert result == "test-app-enabled"

        # Number to string conversion in logic
        result = self.processor.process_string(
            "${{ inputs.count > 0 && str(inputs.count) || 'zero' }}"
        )
        assert result == "100"

        # Boolean to number-like logic
        result = self.processor.process_string("${{ inputs.enabled && 1 || 0 }}")
        assert result == "1"

    def test_environment_variable_expressions(self):
        """Test expressions with environment variables."""
        os.environ["TEST_COUNT"] = "42"
        os.environ["TEST_FLAG"] = "true"
        os.environ["EMPTY_VAR"] = ""

        try:
            # Environment variable math
            result = self.processor.process_string("${{ int(env.TEST_COUNT) * 2 }}")
            assert result == "84"

            # Environment variable fallbacks
            result = self.processor.process_string(
                "${{ env.MISSING || env.TEST_COUNT }}"
            )
            assert result == "42"

            # Empty environment variable fallback
            result = self.processor.process_string("${{ env.EMPTY_VAR || 'fallback' }}")
            assert result == "fallback"

            # Environment variable in conditions
            result = self.processor.process_string(
                "${{ int(env.TEST_COUNT) > 40 && 'high' || 'low' }}"
            )
            assert result == "high"

        finally:
            # Clean up environment
            for var in ["TEST_COUNT", "TEST_FLAG", "EMPTY_VAR"]:
                os.environ.pop(var, None)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Zero values
        processor_zero = TemplateProcessor(
            defined_inputs={"zero": {"type": "number", "default": 0}}, cli_inputs={}
        )
        result = processor_zero.process_string("${{ inputs.zero || 'fallback' }}")
        assert result == "fallback"  # 0 is falsy

        # Empty string values
        processor_empty = TemplateProcessor(
            defined_inputs={"empty": {"type": "string", "default": ""}}, cli_inputs={}
        )
        result = processor_empty.process_string("${{ inputs.empty || 'fallback' }}")
        assert result == "fallback"  # Empty string is falsy

        # Large numbers
        result = self.processor.process_string("${{ inputs.count * 1000000 }}")
        assert result == "100000000"

    def test_quoted_strings_with_special_characters(self):
        """Test expressions with quoted strings containing special characters."""
        # Strings with spaces
        result = self.processor.process_string(
            "${{ inputs.missing || '  spaced value  ' }}"
        )
        assert result == "  spaced value  "

        # Strings with operators (should not be parsed as operators)
        result = self.processor.process_string(
            "${{ inputs.missing || 'value||with||pipes' }}"
        )
        assert result == "value||with||pipes"

        result = self.processor.process_string(
            "${{ inputs.missing || 'value&&with&&amps' }}"
        )
        assert result == "value&&with&&amps"

        # Strings with quotes
        result = self.processor.process_string(
            """${{ inputs.missing || "it's a test" }}"""
        )
        assert result == "it's a test"

    def test_complex_nested_expressions(self):
        """Test deeply nested and complex expressions."""
        # Nested conditions with multiple levels
        result = self.processor.process_string(
            "${{ (inputs.environment == 'prod' && (inputs.count > 1000 && 'high-prod' || 'low-prod')) || (inputs.environment == 'dev' && (inputs.enabled && 'dev-enabled' || 'dev-disabled')) || 'unknown' }}"
        )
        assert result == "dev-enabled"

        # Mathematical expressions with multiple operations
        result = self.processor.process_string(
            "${{ int((inputs.count + 50) * inputs.ratio) + (inputs.enabled && 10 || 5) }}"
        )
        assert result == "85"  # int((100 + 50) * 0.5) + 10 = 75 + 10

    def test_error_handling(self):
        """Test error handling for invalid expressions."""
        # Division by zero should be handled by simpleeval
        with pytest.raises(TemplateError):
            self.processor.process_string("${{ inputs.count / 0 }}")

        # Invalid syntax should raise TemplateError
        with pytest.raises(TemplateError):
            self.processor.process_string("${{ inputs.count + }}")

        # Undefined functions should fail
        with pytest.raises(TemplateError):
            self.processor.process_string("${{ undefined_function(inputs.count) }}")

    def test_whitespace_handling(self):
        """Test expressions with various whitespace patterns."""
        # Spaces around operators
        result = self.processor.process_string(
            "${{   inputs.count   >   50   &&   'yes'   ||   'no'   }}"
        )
        assert result == "yes"

        # Mixed spacing
        result = self.processor.process_string("${{inputs.count>50&&'yes'||'no'}}")
        assert result == "yes"

        # Newlines (if supported)
        result = self.processor.process_string(
            "${{ inputs.count > 50 \n&& 'yes' \n|| 'no' }}"
        )
        assert result == "yes"

    def test_precedence_rules(self):
        """Test operator precedence is correctly handled."""
        # Multiplication before addition
        result = self.processor.process_string("${{ 2 + 3 * 4 }}")
        assert result == "14"  # 2 + (3 * 4) = 14, not (2 + 3) * 4 = 20

        # Comparison before logical AND
        result = self.processor.process_string(
            "${{ inputs.count > 50 && inputs.count < 200 }}"
        )
        assert result == "true"

        # Parentheses override precedence
        result = self.processor.process_string("${{ (2 + 3) * 4 }}")
        assert result == "20"

    def test_type_coercion_and_conversion(self):
        """Test how different types interact in expressions."""
        # String to number comparison (should work with proper conversion)
        os.environ["NUMERIC_STRING"] = "123"
        try:
            result = self.processor.process_string(
                "${{ int(env.NUMERIC_STRING) > inputs.count }}"
            )
            assert result == "true"  # 123 > 100
        finally:
            os.environ.pop("NUMERIC_STRING", None)

        # Boolean in arithmetic context
        result = self.processor.process_string("${{ inputs.enabled + 0 }}")
        assert result == "1"  # True + 0 = 1

        # String concatenation-like behavior
        result = self.processor.process_string(
            "${{ inputs.enabled && inputs.name || 'default' }}"
        )
        assert result == "test-app"  # True && "test-app" = "test-app"
