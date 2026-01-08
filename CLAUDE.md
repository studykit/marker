# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Marker is a high-performance document conversion library that converts PDFs, images, and other document formats (PPTX, DOCX, XLSX, HTML, EPUB) to Markdown, JSON, HTML, and chunks. It uses deep learning models for OCR, layout detection, and optional LLM enhancement.

## Common Commands

```bash
# Installation
poetry install --extras "full"          # Development install with all document formats

# Running tests
poetry run pytest                        # All tests
poetry run pytest tests/test_file.py    # Single file
poetry run pytest -k "test_name"        # Single test by name

# Code quality (pre-commit hooks configured)
pre-commit install                       # Set up hooks
pre-commit run --all-files              # Run ruff linter + formatter

# CLI tools
marker_single /path/to/file.pdf         # Convert single file
marker /path/to/input/folder            # Batch conversion
marker_gui                              # Streamlit interactive app
marker_server --port 8001               # FastAPI server
```

## Architecture

Marker uses a **plugin-based pipeline architecture** with five main component types:

### Pipeline Flow
```
Provider → Builders → Processors → Renderer → Output
```

### Core Components

**Providers** (`marker/providers/`): Extract raw data from source files (PDF, images, PPTX, etc.). Registry pattern maps file types to appropriate providers.

**Builders** (`marker/builders/`): Generate initial document structure from provider data. Key builders: `DocumentBuilder`, `LayoutBuilder`, `OcrBuilder`, `StructureBuilder`.

**Processors** (`marker/processors/`): Transform document blocks. 23+ processor types including LLM-enhanced processors in `processors/llm/`. Each processor implements `__call__(document: Document)`.

**Renderers** (`marker/renderers/`): Convert processed documents to output formats (Markdown, HTML, JSON, chunks).

**Services** (`marker/services/`): LLM integrations (Gemini, Claude, OpenAI, Ollama, etc.) for enhanced processing.

### Document Model

Tree structure: `Document` → `Page` → `Block` (30+ block types defined in `marker/schema/blocks/`)

### Configuration Pattern

Components use annotated type hints for self-documenting config options:
```python
class MyComponent:
    option_name: Annotated[type, "description"] = default_value

    def __init__(self, config: Optional[BaseModel | dict] = None):
        assign_config(self, config)  # Applies config to instance
```

### Entry Points

Main converters in `marker/converters/`: `PdfConverter`, `TableConverter`, `OCRConverter`, `ExtractionConverter`. CLI scripts in `marker/scripts/`.

## Key Files

- `marker/settings.py`: Environment-based config using Pydantic `BaseSettings` (TORCH_DEVICE, OUTPUT_DIR, etc.)
- `marker/util.py`: Core utilities including `strings_to_classes()`, `assign_config()`, math/geometry helpers
- `marker/models.py`: Model initialization and loading
- `marker/config/parser.py`: CLI options and JSON configuration handling

## Extending Marker

- **Custom processors**: Inherit from `BaseProcessor`, implement `__call__(document)`
- **Custom renderers**: Inherit from `BaseRenderer`
- **Custom providers**: Add to `providers/` with registry entry in `registry.py`
- **Custom services**: Inherit from `BaseService`

## Environment Variables

- `TORCH_DEVICE`: Force GPU/CPU/MPS (auto-detects if not set)
- `GOOGLE_API_KEY`: For Gemini LLM service
- `TOKENIZERS_PARALLELISM=false`: Set to prevent warnings
