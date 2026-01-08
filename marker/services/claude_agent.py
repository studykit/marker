import json
import os
import subprocess
import time
import uuid
from typing import Annotated, List

import PIL
from PIL import Image
from pydantic import BaseModel

from marker.logger import get_logger
from marker.schema.blocks import Block
from marker.services import BaseService

logger = get_logger()


class ClaudeAgentService(BaseService):
    """
    LLM service using Claude CLI for document analysis.

    Requires:
    - Claude Code CLI installed and authenticated
    """

    claude_agent_model: Annotated[
        str, "The Claude model to use (e.g., 'sonnet', 'haiku', 'opus')."
    ] = "sonnet"

    claude_agent_timeout_seconds: Annotated[
        int, "Timeout for CLI calls in seconds."
    ] = 120

    def _save_images_to_temp(self, images: List[Image.Image]) -> List[str]:
        """Save images to temporary files and return paths."""
        temp_paths = []
        for img in images:
            temp_path = f"/tmp/claude_img_{uuid.uuid4().hex}.webp"
            img.save(temp_path, format="WEBP")
            temp_paths.append(temp_path)
            logger.debug(f"Saved temp image: {temp_path}")
        return temp_paths

    def _cleanup_temp_files(self, paths: List[str]):
        """Delete temporary files."""
        for path in paths:
            try:
                os.remove(path)
                logger.debug(f"Cleaned up temp file: {path}")
            except OSError as e:
                logger.debug(f"Failed to clean up {path}: {e}")

    def _build_prompt_with_images(self, prompt: str, image_paths: List[str]) -> str:
        """Build prompt with image file references."""
        if not image_paths:
            return prompt

        image_refs = "\n".join([
            f"- Image {i+1}: {path}"
            for i, path in enumerate(image_paths)
        ])
        return f"""The following images are provided for analysis. Use the Read tool to view them:
{image_refs}

{prompt}"""

    def _call_cli(
        self,
        prompt: str,
        response_schema: type[BaseModel],
        timeout: int
    ) -> tuple[dict, int]:
        """Call Claude CLI directly."""
        schema_json = json.dumps(response_schema.model_json_schema())

        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--json-schema", schema_json,
            "--tools", "Read",
            "--permission-mode", "bypassPermissions",
            "--model", self.claude_agent_model,
        ]

        logger.debug(f"Calling Claude CLI with model: {self.claude_agent_model}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown CLI error"
            raise RuntimeError(f"Claude CLI error: {error_msg}")

        response = json.loads(result.stdout)

        # Extract structured output
        structured_output = response.get("structured_output", {})

        # Calculate token usage
        usage = response.get("usage", {})
        total_tokens = (
            usage.get("input_tokens", 0) +
            usage.get("cache_creation_input_tokens", 0) +
            usage.get("cache_read_input_tokens", 0) +
            usage.get("output_tokens", 0)
        )

        logger.debug(f"CLI response: is_error={response.get('is_error')}, tokens={total_tokens}")

        return structured_output, total_tokens

    def __call__(
        self,
        prompt: str,
        image: PIL.Image.Image | List[PIL.Image.Image] | None,
        block: Block | None,
        response_schema: type[BaseModel],
        max_retries: int | None = None,
        timeout: int | None = None,
    ) -> dict:
        if max_retries is None:
            max_retries = self.max_retries

        if timeout is None:
            timeout = self.claude_agent_timeout_seconds

        # Save images to temp files
        temp_paths = []
        if image:
            images = image if isinstance(image, list) else [image]
            temp_paths = self._save_images_to_temp(images)

        try:
            # Build prompt with image references
            full_prompt = self._build_prompt_with_images(prompt, temp_paths)

            # Retry loop
            total_tries = max_retries + 1
            for tries in range(1, total_tries + 1):
                try:
                    result_dict, total_tokens = self._call_cli(
                        full_prompt, response_schema, timeout
                    )

                    # Track token usage
                    if block and total_tokens > 0:
                        block.update_metadata(
                            llm_tokens_used=total_tokens, llm_request_count=1
                        )

                    # Return result if we got structured output
                    if result_dict:
                        return result_dict

                    # Empty response - retry
                    if tries < total_tries:
                        logger.warning(
                            f"Empty response from Claude CLI. Retrying... "
                            f"(Attempt {tries}/{total_tries})"
                        )
                        continue

                except subprocess.TimeoutExpired:
                    if tries == total_tries:
                        logger.error(
                            f"Timeout error. Max retries reached. Giving up. "
                            f"(Attempt {tries}/{total_tries})"
                        )
                        break
                    wait_time = tries * self.retry_wait_time
                    logger.warning(
                        f"Timeout error. Retrying in {wait_time} seconds... "
                        f"(Attempt {tries}/{total_tries})"
                    )
                    time.sleep(wait_time)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse CLI response: {e}")
                    break

                except RuntimeError as e:
                    error_str = str(e).lower()
                    # Check for rate limiting or transient errors
                    if "rate" in error_str or "limit" in error_str:
                        if tries == total_tries:
                            logger.error(
                                f"Rate limit error: {e}. Max retries reached. "
                                f"(Attempt {tries}/{total_tries})"
                            )
                            break
                        wait_time = tries * self.retry_wait_time
                        logger.warning(
                            f"Rate limit error: {e}. Retrying in {wait_time} seconds... "
                            f"(Attempt {tries}/{total_tries})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Error during Claude CLI call: {e}")
                        break

                except Exception as e:
                    logger.error(f"Unexpected error during Claude CLI call: {e}")
                    break

            return {}

        finally:
            # Clean up temp files
            self._cleanup_temp_files(temp_paths)
