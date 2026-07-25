"""Tests for prompt injection defenses."""
import pytest

from app.services.prompt_armor import (
    IMMUTABLE_CONTENT_RULES,
    IMMUTABLE_STRATEGY_RULES,
    OutputValidationError,
    build_system_blocks,
    check_canary,
    generate_canary,
    validate_content_output,
    validate_strategy_output,
)


class TestCanary:
    def test_generate_canary_format(self):
        canary = generate_canary()
        assert canary.startswith("CANARY-")
        assert len(canary) == 7 + 16  # "CANARY-" + 16 chars

    def test_generate_canary_unique(self):
        canaries = {generate_canary() for _ in range(100)}
        assert len(canaries) == 100

    def test_check_canary_not_leaked(self):
        canary = generate_canary()
        assert check_canary("clean output text", canary) is False

    def test_check_canary_leaked(self):
        canary = generate_canary()
        output = f"Here is the canary: {canary}"
        assert check_canary(output, canary) is True


class TestBuildSystemBlocks:
    def test_returns_three_blocks(self):
        blocks = build_system_blocks(
            immutable_rules="Rules {canary}",
            user_prompt="user stuff",
            fixed_tail="tail",
            canary="CANARY-test123",
        )
        assert len(blocks) == 3

    def test_block_1_has_cache_control(self):
        blocks = build_system_blocks(
            immutable_rules="Rules {canary}",
            user_prompt="user stuff",
            fixed_tail="tail",
            canary="CANARY-test123",
        )
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in blocks[1]
        assert "cache_control" not in blocks[2]

    def test_canary_embedded_in_block_1(self):
        canary = "CANARY-abc123"
        blocks = build_system_blocks(
            immutable_rules="Rules {canary}",
            user_prompt="user stuff",
            fixed_tail="tail",
            canary=canary,
        )
        assert canary in blocks[0]["text"]

    def test_user_prompt_wrapped_in_xml(self):
        blocks = build_system_blocks(
            immutable_rules="Rules {canary}",
            user_prompt="my custom prompt",
            fixed_tail="tail",
            canary="CANARY-x",
        )
        assert "<user_customization>" in blocks[1]["text"]
        assert "</user_customization>" in blocks[1]["text"]
        assert "my custom prompt" in blocks[1]["text"]

    def test_fixed_tail_in_block_3(self):
        blocks = build_system_blocks(
            immutable_rules="Rules {canary}",
            user_prompt="user stuff",
            fixed_tail="OUTPUT FORMAT HERE",
            canary="CANARY-x",
        )
        assert blocks[2]["text"] == "OUTPUT FORMAT HERE"

    def test_immutable_content_rules_format(self):
        canary = generate_canary()
        blocks = build_system_blocks(
            immutable_rules=IMMUTABLE_CONTENT_RULES,
            user_prompt="test",
            fixed_tail="tail",
            canary=canary,
        )
        assert canary in blocks[0]["text"]
        assert "<user_customization>" in blocks[1]["text"]

    def test_immutable_strategy_rules_format(self):
        canary = generate_canary()
        blocks = build_system_blocks(
            immutable_rules=IMMUTABLE_STRATEGY_RULES,
            user_prompt="test",
            fixed_tail="tail",
            canary=canary,
        )
        assert canary in blocks[0]["text"]


class TestValidateContentOutput:
    def test_valid_output(self):
        data = {
            "script": "some script",
            "description": "some description",
            "editor_instructions": "some instructions",
        }
        assert validate_content_output(data) == data

    def test_missing_key(self):
        data = {"script": "x", "description": "y"}
        with pytest.raises(OutputValidationError, match="editor_instructions"):
            validate_content_output(data)

    def test_empty_string(self):
        data = {
            "script": "",
            "description": "y",
            "editor_instructions": "z",
        }
        with pytest.raises(OutputValidationError, match="script"):
            validate_content_output(data)

    def test_whitespace_only(self):
        data = {
            "script": "   ",
            "description": "y",
            "editor_instructions": "z",
        }
        with pytest.raises(OutputValidationError, match="script"):
            validate_content_output(data)

    def test_wrong_type(self):
        data = {
            "script": 123,
            "description": "y",
            "editor_instructions": "z",
        }
        with pytest.raises(OutputValidationError, match="script"):
            validate_content_output(data)

    def test_extra_keys_allowed(self):
        data = {
            "script": "x",
            "description": "y",
            "editor_instructions": "z",
            "extra_field": "ignored",
        }
        assert validate_content_output(data) == data


class TestValidateStrategyOutput:
    def test_valid_output(self):
        data = {
            "virality_breakdown": "some text",
            "hook_variants": ["a", "b", "c"],
        }
        assert validate_strategy_output(data) == data

    def test_missing_virality_breakdown(self):
        data = {"hook_variants": ["a"]}
        with pytest.raises(OutputValidationError, match="virality_breakdown"):
            validate_strategy_output(data)

    def test_empty_virality_breakdown(self):
        data = {
            "virality_breakdown": "",
            "hook_variants": ["a"],
        }
        with pytest.raises(OutputValidationError, match="virality_breakdown"):
            validate_strategy_output(data)

    def test_missing_hook_variants(self):
        data = {"virality_breakdown": "text"}
        with pytest.raises(OutputValidationError, match="hook_variants"):
            validate_strategy_output(data)

    def test_empty_hook_variants(self):
        data = {
            "virality_breakdown": "text",
            "hook_variants": [],
        }
        with pytest.raises(OutputValidationError, match="hook_variants"):
            validate_strategy_output(data)

    def test_extra_keys_allowed(self):
        data = {
            "virality_breakdown": "text",
            "hook_variants": ["a"],
            "comments_strategy": {},
        }
        assert validate_strategy_output(data) == data
