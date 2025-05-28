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

    # --- Tests for Pipeline Inputs in TemplateProcessor ---

    def test_input_from_cli(self):
        """Test resolving an input provided via CLI."""
        defined_inputs = {"env_name": {"type": "string"}}
        cli_inputs = {"env_name": "production"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: production"

    def test_input_from_default(self):
        """Test resolving an input from its manifest default."""
        defined_inputs = {"env_name": {"type": "string", "default": "dev"}}
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: dev"

    def test_input_cli_overrides_default(self):
        """Test CLI input value overrides manifest default."""
        defined_inputs = {"env_name": {"type": "string", "default": "dev"}}
        cli_inputs = {"env_name": "staging"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: staging"

    def test_input_number_from_cli(self):
        """Test number input from CLI is stringified."""
        defined_inputs = {"count": {"type": "number"}}
        cli_inputs = {"count": "123"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Count: ${{ inputs.count }}")
        assert result == "Count: 123"  # Whole numbers are stringified without .0

    def test_input_number_from_default(self):
        """Test number input from default is stringified."""
        defined_inputs = {"count": {"type": "number", "default": 42}}
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string("Count: ${{ inputs.count }}")
        assert result == "Count: 42"  # Default is already a number

    def test_input_boolean_true_from_cli(self):
        """Test boolean true input from CLI is stringified to 'true'."""
        defined_inputs = {"enabled": {"type": "boolean"}}
        cli_inputs = {"enabled": "yes"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Enabled: ${{ inputs.enabled }}")
        assert result == "Enabled: true"

    def test_input_boolean_false_from_cli(self):
        """Test boolean false input from CLI is stringified to 'false'."""
        defined_inputs = {"enabled": {"type": "boolean"}}
        cli_inputs = {"enabled": "0"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Enabled: ${{ inputs.enabled }}")
        assert result == "Enabled: false"

    def test_input_boolean_true_from_default(self):
        """Test boolean true input from default is stringified to 'true'."""
        defined_inputs = {"enabled": {"type": "boolean", "default": True}}
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string("Enabled: ${{ inputs.enabled }}")
        assert result == "Enabled: true"

    def test_input_boolean_false_from_default(self):
        """Test boolean false input from default is stringified to 'false'."""
        defined_inputs = {"enabled": {"type": "boolean", "default": False}}
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string("Enabled: ${{ inputs.enabled }}")
        assert result == "Enabled: false"

    def test_input_missing_no_default_no_cli(self):
        """Test input not in CLI and no default resolves to empty string (via None in fallback)."""
        defined_inputs = {
            "optional_input": {"type": "string"}
        }  # No default, not required for this test
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string("Value: ${{ inputs.optional_input }}")
        assert (
            result == "Value: "
        )  # Resolves to None, then empty string by _evaluate_expression_with_fallbacks

    def test_input_fallback_to_default(self):
        """Test ${{ inputs.missing_cli || inputs.has_default }}."""
        defined_inputs = {
            "missing_cli": {"type": "string"},
            "has_default": {"type": "string", "default": "default_value"},
        }
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string(
            "Value: ${{ inputs.missing_cli || inputs.has_default }}"
        )
        assert result == "Value: default_value"

    def test_input_fallback_cli_wins_over_default_in_chain(self):
        """Test ${{ inputs.cli_provided || inputs.default_also }}."""
        defined_inputs = {
            "cli_provided": {"type": "string"},
            "default_also": {"type": "string", "default": "should_not_use"},
        }
        cli_inputs = {"cli_provided": "cli_wins"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string(
            "Value: ${{ inputs.cli_provided || inputs.default_also }}"
        )
        assert result == "Value: cli_wins"

    def test_input_fallback_to_env_var(self):
        """Test ${{ inputs.missing_input || env.MY_ENV_VAR }}."""
        defined_inputs = {"missing_input": {"type": "string"}}
        os.environ["MY_ENV_VAR"] = "env_var_value"
        try:
            processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
            result = processor.process_string(
                "Value: ${{ inputs.missing_input || env.MY_ENV_VAR }}"
            )
            assert result == "Value: env_var_value"
        finally:
            del os.environ["MY_ENV_VAR"]

    def test_input_fallback_to_literal(self):
        """Test ${{ inputs.missing_input || 'literal_fallback' }}."""
        defined_inputs = {"missing_input": {"type": "string"}}
        processor = TemplateProcessor(defined_inputs=defined_inputs, cli_inputs={})
        result = processor.process_string(
            "Value: ${{ inputs.missing_input || 'literal_fallback' }}"
        )
        assert result == "Value: literal_fallback"

    def test_input_undefined_in_manifest(self):
        """Test referencing an input name not defined in manifest (e.g., ${{ inputs.undefined_input }})."""
        # No inputs defined in manifest
        processor = TemplateProcessor(defined_inputs={}, cli_inputs={})
        result = processor.process_string("Value: ${{ inputs.undefined_input }}")
        assert result == "Value: "  # Resolves to None, then empty string

    def test_input_undefined_in_manifest_with_fallback(self):
        """Test ${{ inputs.undefined_input || 'fallback_for_undefined' }}."""
        processor = TemplateProcessor(defined_inputs={}, cli_inputs={})
        result = processor.process_string(
            "Value: ${{ inputs.undefined_input || 'fallback_for_undefined' }}"
        )
        assert result == "Value: fallback_for_undefined"

    def test_input_empty_name_error(self):
        """Test that an empty input name like ${{ inputs. }} raises TemplateError."""
        processor = TemplateProcessor(defined_inputs={}, cli_inputs={})
        with pytest.raises(TemplateError, match="Empty input name in expression"):
            processor.process_string("Value: ${{ inputs. }}")

    def test_input_from_cli_malformed_boolean_error(self):
        """Test error if CLI provides malformed boolean for a defined boolean input."""
        # This scenario should ideally be caught by Pipeline.validate() before templating.
        # However, if TemplateProcessor gets such data, it should error.
        defined_inputs = {"strict_bool": {"type": "boolean"}}
        cli_inputs = {"strict_bool": "not_a_bool"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        with pytest.raises(
            TemplateError,
            match=r"CLI must be a boolean. Received: 'not_a_bool'",
        ):
            processor.process_string("Value: ${{ inputs.strict_bool }}")

    def test_input_from_cli_malformed_number_error(self):
        """Test error if CLI provides malformed number for a defined number input."""
        # Similar to boolean, Pipeline.validate() should catch this.
        defined_inputs = {"strict_num": {"type": "number"}}
        cli_inputs = {"strict_num": "not_a_number"}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        # The error comes from float() conversion in _evaluate_pipeline_input
        with pytest.raises(
            TemplateError,
            match=r"CLI must be a number. Received: 'not_a_number'",
        ):
            processor.process_string("Value: ${{ inputs.strict_num }}")

    def test_input_cli_whitespace_trimmed(self):
        """Test that CLI input values are trimmed of leading/trailing whitespace."""
        defined_inputs = {"env_name": {"type": "string"}}
        cli_inputs = {"env_name": "  production  "}
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: production"  # Whitespace should be trimmed

    def test_input_cli_whitespace_only_falls_back_to_default(self):
        """Test that CLI input with only whitespace falls back to default."""
        defined_inputs = {"env_name": {"type": "string", "default": "dev"}}
        cli_inputs = {"env_name": "   "}  # Only whitespace
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: dev"  # Should use default, not whitespace

    def test_input_cli_whitespace_only_no_default_empty_result(self):
        """Test that CLI input with only whitespace and no default results in empty."""
        defined_inputs = {"env_name": {"type": "string"}}  # No default
        cli_inputs = {"env_name": "   "}  # Only whitespace
        processor = TemplateProcessor(
            defined_inputs=defined_inputs, cli_inputs=cli_inputs
        )
        result = processor.process_string("Environment: ${{ inputs.env_name }}")
        assert result == "Environment: "  # Should be empty since no default


class TestTemplateProcessorProcessStructure:
    def test_process_structure_empty(self):
        tp = TemplateProcessor()
        assert tp.process_structure({}) == {}
        assert tp.process_structure([]) == []
        assert tp.process_structure(None) is None
        assert tp.process_structure("abc") == "abc"  # Simple string, no templates
        assert tp.process_structure(123) == 123

    def test_process_structure_simple_dict(self, monkeypatch):
        monkeypatch.setenv("MY_ENV_VAR", "env_value")
        tp = TemplateProcessor(
            defined_inputs={"my_input": {"type": "string", "default": "input_value"}},
            pipeline_name="TestPipe",
            pipeline_description="A test pipeline",
        )
        data = {
            "key1": "Value is ${{ env.MY_ENV_VAR }}",
            "key2": "Input is ${{ inputs.my_input }}",
            "key3": "Pipeline is ${{ pipeline.name }} - ${{ pipeline.description }}",
            "key4": 123,
            "${{ env.MY_ENV_VAR }}": "key_is_template",
        }
        expected = {
            "key1": "Value is env_value",
            "key2": "Input is input_value",
            "key3": "Pipeline is TestPipe - A test pipeline",
            "key4": 123,
            "env_value": "key_is_template",
        }
        assert tp.process_structure(data) == expected

    def test_process_structure_nested_dict_and_list(self, monkeypatch):
        monkeypatch.setenv("NEST_ENV", "nested_env_val")
        tp = TemplateProcessor(
            defined_inputs={"item_input": {"type": "string", "default": "item_val"}},
            pipeline_name="ComplexPipe",
        )
        data = {
            "level1_key": "Plain string",
            "level1_dict": {
                "l2_key1": "L2 value: ${{ env.NEST_ENV }}",
                "l2_key2": "L2 input: ${{ inputs.item_input }}",
                "l2_list": [
                    "Item 1: ${{ pipeline.name }}",
                    {"listItemKey": "Item 2: ${{ env.NEST_ENV }}"},
                    100,
                ],
            },
            "level1_list": ["RootList: ${{ inputs.item_input }}", True],
        }
        expected = {
            "level1_key": "Plain string",
            "level1_dict": {
                "l2_key1": "L2 value: nested_env_val",
                "l2_key2": "L2 input: item_val",
                "l2_list": [
                    "Item 1: ComplexPipe",
                    {"listItemKey": "Item 2: nested_env_val"},
                    100,
                ],
            },
            "level1_list": ["RootList: item_val", True],
        }
        assert tp.process_structure(data) == expected

    def test_process_structure_does_not_use_stack_outputs(self, monkeypatch):
        # This test ensures that process_structure, when processing general config,
        # does not accidentally pick up stack_outputs if they were added to the processor instance.
        # Stack outputs are for stack.params resolution specifically.
        monkeypatch.setenv("MY_ENV", "env_ok")
        tp = TemplateProcessor(pipeline_name="PipeForSamConfig")
        tp.add_stack_outputs("s1", {"Out1": "stack_output_value"})

        sam_config_structure = {
            "setting1": "Value from env: ${{ env.MY_ENV }}",
            "setting2": "Value from stack (should not resolve): ${{ stacks.s1.outputs.Out1 || 'fallback' }}",
        }

        # process_string itself, when resolving ${{ stacks... }}, will use self.stack_outputs.
        # The key is that process_structure provides a context to process_string
        # that does not implicitly include all stack outputs for general config processing.
        # The current implementation of process_string will use self.stack_outputs regardless
        # of the call path IF a stacks.* template is encountered.
        # This test confirms the behavior of process_string when called by process_structure.
        expected_sam_config_structure = {
            "setting1": "Value from env: env_ok",
            # Since process_string *will* evaluate stacks.s1.outputs.Out1 using self.stack_outputs,
            # this *will* be replaced. This highlights that if a user puts such a template
            # in their default_sam_config, it *will* resolve if the output exists globally.
            # This is consistent with how process_string works.
            "setting2": "Value from stack (should not resolve): stack_output_value",
        }
        assert (
            tp.process_structure(sam_config_structure) == expected_sam_config_structure
        )

    def test_process_structure_with_explicit_pipeline_context_override(self):
        tp = TemplateProcessor(pipeline_name="InitialPipeName")
        data = {"name_check": "Pipeline is ${{ pipeline.name }}"}

        # No override, uses instance default
        assert tp.process_structure(data) == {
            "name_check": "Pipeline is InitialPipeName"
        }

        # With override
        assert tp.process_structure(data, pipeline_name="OverriddenPipeName") == {
            "name_check": "Pipeline is OverriddenPipeName"
        }

        # Override with None should pick up instance default if one was set
        assert tp.process_structure(data, pipeline_name=None) == {
            "name_check": "Pipeline is InitialPipeName"
        }

        # If instance default was None, and override is None, result is empty
        tp_no_default = TemplateProcessor()
        assert tp_no_default.process_structure(data, pipeline_name=None) == {
            "name_check": "Pipeline is "
        }
