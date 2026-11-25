"""Load, validate, dump, and export JSON Schema for DoneGate contracts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from donegate.contract.models import SCHEMA_VERSION, Contract


class ContractValidationError(Exception):
    """Raised when a done.yaml contract fails YAML parsing or schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or [message]


def parse_contract_yaml(raw_yaml: str) -> Contract:
    """Parse raw YAML text into a validated Contract."""
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ContractValidationError(f"Invalid YAML syntax: {exc}") from exc

    if not isinstance(data, dict):
        raise ContractValidationError("Contract root must be a YAML mapping/object")

    try:
        return Contract.model_validate(data)
    except ValidationError as exc:
        messages = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        joined = "; ".join(messages)
        raise ContractValidationError(f"Contract validation failed: {joined}", messages) from exc


def load_contract(path: Path | str) -> Contract:
    """Load and validate a done.yaml contract from disk."""
    contract_path = Path(path)
    if not contract_path.exists():
        raise ContractValidationError(f"Contract file not found: {contract_path}")
    return parse_contract_yaml(contract_path.read_text(encoding="utf-8"))


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text to a file via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def dump_contract(contract: Contract, path: Path | str) -> None:
    """Serialize a Contract to YAML and write it atomically."""
    yaml_text = yaml.safe_dump(
        contract.to_yaml_dict(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    atomic_write_text(Path(path), yaml_text)


def export_contract_schema() -> dict[str, Any]:
    """Export versioned JSON Schema for the DoneGate Contract."""
    schema = Contract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["x-donegate-schema-version"] = SCHEMA_VERSION
    return schema
