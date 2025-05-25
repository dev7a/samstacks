"""
Tests for the templating module.
"""

import os
import pytest

from samstacks.templating import TemplateProcessor
from samstacks.exceptions import TemplateError


class TestTemplateProcessor:
    """Test cases for TemplateProcessor."""

    def test_no_substitution(self):
        """Test that strings without templates are returned unchanged."""
        processor = TemplateProcessor()
        result = processor.process_string("hello world")
        assert result == "hello world"

    def test_env_substitution(self):
        """Test environment variable substitution."""
        processor = TemplateProcessor()

        # Set a test environment variable
        os.environ["TEST_VAR"] = "test_value"
        try:
            result = processor.process_string("Hello ${{ env.TEST_VAR }}!")
            assert result == "Hello test_value!"
        finally:
            del os.environ["TEST_VAR"]

    def test_env_substitution_missing_var(self):
        """Test that missing environment variables are replaced with empty string."""
        processor = TemplateProcessor()
        result = processor.process_string("Hello ${{ env.NONEXISTENT_VAR }}!")
        assert result == "Hello !"

    def test_stack_output_substitution(self):
        """Test stack output substitution."""
        processor = TemplateProcessor()

        # Add some mock stack outputs
        processor.add_stack_outputs("test-stack", {"ApiUrl": "https://api.example.com"})

        result = processor.process_string(
            "API URL: ${{ stacks.test-stack.outputs.ApiUrl }}"
        )
        assert result == "API URL: https://api.example.com"

    def test_stack_output_missing_stack(self):
        """Test that referencing outputs from non-existent stack results in empty string (or fallback)."""
        processor = TemplateProcessor()

        # Test without fallback
        result = processor.process_string(
            "Value: ${{ stacks.missing-stack.outputs.SomeOutput }}"
        )
        assert result == "Value: "

        # Test with fallback
        result_with_fallback = processor.process_string(
            "Value: ${{ stacks.missing-stack.outputs.SomeOutput || 'default_if_stack_missing' }}"
        )
        assert result_with_fallback == "Value: default_if_stack_missing"

    def test_stack_output_missing_output(self):
        """Test that missing stack outputs with no fallback result in empty string."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("test-stack", {"ApiUrl": "https://api.example.com"})

        # No fallback, should result in empty string
        result = processor.process_string(
            "Value: ${{ stacks.test-stack.outputs.MissingOutput }}"
        )
        assert result == "Value: "

    def test_stack_output_malformed_expression(self):
        """Test error when stack output expression is malformed."""
        processor = TemplateProcessor()
        with pytest.raises(
            TemplateError, match="Invalid stack output expression format"
        ):
            processor.process_string("${{ stacks.test-stack.ApiUrl }}")
        with pytest.raises(
            TemplateError, match="Invalid stack output expression format"
        ):
            processor.process_string("${{ stacks.test-stack.outputs }}")
        with pytest.raises(
            TemplateError, match="Invalid stack output expression format"
        ):
            processor.process_string("${{ stacks.outputs.ApiUrl }}")

    def test_multiple_substitutions(self):
        """Test multiple substitutions in one string."""
        processor = TemplateProcessor()

        os.environ["TEST_ENV"] = "production"
        processor.add_stack_outputs("api-stack", {"Endpoint": "https://api.prod.com"})

        try:
            template = "Environment: ${{ env.TEST_ENV }}, API: ${{ stacks.api-stack.outputs.Endpoint }}"
            result = processor.process_string(template)
            assert result == "Environment: production, API: https://api.prod.com"
        finally:
            del os.environ["TEST_ENV"]

    def test_whitespace_handling(self):
        """Test that whitespace in template expressions is handled correctly."""
        processor = TemplateProcessor()
        os.environ["TEST_VAR"] = "value"

        try:
            # Test various whitespace scenarios
            result1 = processor.process_string("${{env.TEST_VAR}}")
            result2 = processor.process_string("${{ env.TEST_VAR }}")
            result3 = processor.process_string("${{  env.TEST_VAR  }}")

            assert result1 == "value"
            assert result2 == "value"
            assert result3 == "value"
        finally:
            del os.environ["TEST_VAR"]

    def test_simple_fallback_env_var_missing(self):
        """Test ${{ env.UNSET_VAR || 'default_value' }} - env var missing."""
        processor = TemplateProcessor()
        result = processor.process_string(
            "Value: ${{ env.UNSET_VAR || 'default_value' }}"
        )
        assert result == "Value: default_value"

    def test_simple_fallback_env_var_exists(self):
        """Test ${{ env.EXISTING_VAR || 'default_value' }} - env var exists."""
        processor = TemplateProcessor()
        os.environ["EXISTING_VAR"] = "actual_value"
        try:
            result = processor.process_string(
                "Value: ${{ env.EXISTING_VAR || 'default_value' }}"
            )
            assert result == "Value: actual_value"
        finally:
            del os.environ["EXISTING_VAR"]

    def test_simple_fallback_env_var_empty(self):
        """Test ${{ env.EMPTY_VAR || 'default_value' }} - env var is empty string."""
        processor = TemplateProcessor()
        os.environ["EMPTY_VAR"] = ""
        try:
            result = processor.process_string(
                "Value: ${{ env.EMPTY_VAR || 'default_value' }}"
            )
            assert result == "Value: default_value"
        finally:
            del os.environ["EMPTY_VAR"]

    def test_chained_fallbacks_all_missing(self):
        """Test ${{ env.UNSET1 || env.UNSET2 || 'default' }} - all missing."""
        processor = TemplateProcessor()
        result = processor.process_string(
            "Value: ${{ env.UNSET1 || env.UNSET2 || 'default' }}"
        )
        assert result == "Value: default"

    def test_chained_fallbacks_middle_exists(self):
        """Test ${{ env.UNSET1 || env.EXISTING || 'default' }} - middle exists."""
        processor = TemplateProcessor()
        os.environ["EXISTING_MIDDLE"] = "middle_value"
        try:
            result = processor.process_string(
                "Value: ${{ env.UNSET_AGAIN || env.EXISTING_MIDDLE || 'final_default' }}"
            )
            assert result == "Value: middle_value"
        finally:
            del os.environ["EXISTING_MIDDLE"]

    def test_chained_fallbacks_first_exists(self):
        """Test ${{ env.EXISTING || env.UNSET1 || 'default' }} - first exists."""
        processor = TemplateProcessor()
        os.environ["FIRST_EXISTING"] = "first_value"
        try:
            result = processor.process_string(
                "Value: ${{ env.FIRST_EXISTING || env.NEVER_REACHED || 'not_this_default' }}"
            )
            assert result == "Value: first_value"
        finally:
            del os.environ["FIRST_EXISTING"]

    def test_fallback_with_stack_output_exists(self):
        """Test ${{ stacks.s1.outputs.OUT1 || 'default' }} - stack output exists."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("s1", {"OUT1": "stack_value"})
        result = processor.process_string(
            "Value: ${{ stacks.s1.outputs.OUT1 || 'default_value' }}"
        )
        assert result == "Value: stack_value"

    def test_fallback_with_stack_output_missing(self):
        """Test ${{ stacks.s1.outputs.MISSING || 'default' }} - stack output missing."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("s1", {"EXISTING_OUT": "val"})
        result = processor.process_string(
            "Value: ${{ stacks.s1.outputs.MISSING_OUT || 'default_for_stack' }}"
        )
        assert result == "Value: default_for_stack"

    def test_fallback_stack_missing_entirely(self):
        """Test ${{ stacks.MISSING_STACK.outputs.OUT || 'default' }} - entire stack missing."""
        processor = TemplateProcessor()
        result = processor.process_string(
            "Value: ${{ stacks.MISSING_STACK.outputs.ANY_OUT || 'stack_is_gone' }}"
        )
        assert result == "Value: stack_is_gone"

    def test_mixed_fallbacks_env_then_stack_then_literal(self):
        """Test ${{ env.UNSET1 || stacks.s1.outputs.MISSING || 'default' }}."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("s1", {"EXISTING_OUT": "val"})
        result = processor.process_string(
            "Value: ${{ env.TOTALLY_UNSET || stacks.s1.outputs.NON_EXISTENT_OUTPUT || 'literal_wins' }}"
        )
        assert result == "Value: literal_wins"

    def test_mixed_fallbacks_stack_then_env_then_literal(self):
        """Test ${{ stacks.s1.outputs.ACTUAL_OUT || env.UNSET1 || 'default' }}."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("s1", {"ACTUAL_OUT": "stack_out_value"})
        os.environ["SHOULD_NOT_BE_USED"] = "env_val"
        try:
            result = processor.process_string(
                "Value: ${{ stacks.s1.outputs.ACTUAL_OUT || env.SHOULD_NOT_BE_USED || 'literal_fallback' }}"
            )
            assert result == "Value: stack_out_value"
        finally:
            del os.environ["SHOULD_NOT_BE_USED"]

    def test_literal_only_fallback(self):
        """Test ${{ 'just_a_literal' }} - though not typical with ||, test its resolution."""
        processor = TemplateProcessor()
        result = processor.process_string("Value: ${{ 'just_a_literal' }}")
        assert result == "Value: just_a_literal"

    def test_empty_literal_as_fallback(self):
        """Test ${{ env.UNSET_VAR || \'\' }} - fallback to empty literal."""
        processor = TemplateProcessor()
        result = processor.process_string("Value: ${{ env.UNSET_VAR || '' }}")
        # The default is an empty string, which is falsy, but it's the resolved value.
        assert result == "Value: "

    def test_fallback_chain_ends_with_empty_literal(self):
        """Test ${{ env.UNSET1 || env.UNSET2 || \'\' }} - chain ends with empty."""
        processor = TemplateProcessor()
        result = processor.process_string(
            "Value: ${{ env.UNSET1 || env.UNSET2 || '' }}"
        )
        assert result == "Value: "

    def test_fallback_chain_with_empty_env_var_then_literal(self):
        """Test ${{ env.EMPTY_VAR || 'default' }} - empty env var is falsy."""
        processor = TemplateProcessor()
        os.environ["EMPTY_VAR"] = ""
        try:
            result = processor.process_string(
                "Value: ${{ env.EMPTY_VAR || 'default_val' }}"
            )
            assert result == "Value: default_val"
        finally:
            del os.environ["EMPTY_VAR"]

    def test_no_fallback_unresolved_env(self):
        """Test ${{ env.UNSET_VAR_NO_FALLBACK }} results in empty string."""
        processor = TemplateProcessor()
        result = processor.process_string("Value: ${{ env.UNSET_VAR_NO_FALLBACK }}")
        assert result == "Value: "

    def test_no_fallback_unresolved_stack_output(self):
        """Test ${{ stacks.s1.outputs.UNSET_OUT_NO_FALLBACK }} results in empty string."""
        processor = TemplateProcessor()
        processor.add_stack_outputs("s1", {"EXISTING": "val"})
        result = processor.process_string(
            "Value: ${{ stacks.s1.outputs.UNSET_OUT_NO_FALLBACK }}"
        )
        assert result == "Value: "

    def test_complex_whitespace_with_fallbacks(self):
        """Test fallback chains with complex whitespace."""
        processor = TemplateProcessor()
        os.environ["MY_VAL"] = "my_actual_value"
        try:
            result = processor.process_string(
                "Value: ${{  env.UNSET_FIRST  ||  env.MY_VAL   ||   'some default'  }}"
            )
            assert result == "Value: my_actual_value"
            result2 = processor.process_string(
                "Value: ${{env.STILL_UNSET||stacks.s1.outputs.MISSING ||   '  spaced default '  }}"
            )
            assert result2 == "Value:   spaced default "
        finally:
            del os.environ["MY_VAL"]

    def test_literal_with_pipe_character_not_as_operator(self):
        """Test that a literal string containing || is not treated as operator."""
        processor = TemplateProcessor()
        result = processor.process_string("Value: ${{ 'hello || world' }}")
        assert result == "Value: hello || world"

    def test_double_quotes_literal(self):
        """Test fallback with double quoted literal."""
        processor = TemplateProcessor()
        result = processor.process_string(
            'Value: ${{ env.UNSET_VAR || "double_quote_default" }}'
        )
        assert result == "Value: double_quote_default"

    def test_fallback_to_env_var_that_is_empty(self):
        """Test ${{ env.UNSET1 || env.EMPTY_VAR_FOR_FB || \'default\' }} where EMPTY_VAR_FOR_FB is \"."""
        processor = TemplateProcessor()
        os.environ["EMPTY_VAR_FOR_FB"] = ""
        try:
            result = processor.process_string(
                "Value: ${{ env.UNSET1 || env.EMPTY_VAR_FOR_FB || 'final_default' }}"
            )
            # EMPTY_VAR_FOR_FB is "", so it's falsy, should go to final_default
            assert result == "Value: final_default"
        finally:
            del os.environ["EMPTY_VAR_FOR_FB"]

    def test_fallback_chain_all_empty_strings(self):
        """Test ${{ env.EMPTY1 || env.EMPTY2 || \'\' }}. Should resolve to last empty string."""
        processor = TemplateProcessor()
        os.environ["EMPTY1"] = ""
        os.environ["EMPTY2"] = ""
        try:
            result = processor.process_string(
                "Value: ${{ env.EMPTY1 || env.EMPTY2 || '' }}"
            )
            assert result == "Value: "  # Last part is '', which is returned
        finally:
            del os.environ["EMPTY1"]
            del os.environ["EMPTY2"]
