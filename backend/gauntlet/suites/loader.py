"""ARC-015 suite registry logic — parse, validate, canonicalise and hash suites, personas, condition and
threshold profiles (SRS-FR-020..023, -050, -090).

Nothing invalid crosses this boundary. Validation errors name the YAML line and column of the first
offending node (SRS-FR-020). YAML is loaded with the safe loader: scenarios are data, never code
(SRS-SEC-007). A suite's version hash is SHA-256 over its canonical JSON (sorted keys, no insignificant
whitespace), so semantically identical suites hash identically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from gauntlet.common.paths import SUITES_DIR
from gauntlet.media.chaos import ChaosParams, ConditionError
from gauntlet.scoring.profile import ProfileError, ThresholdProfile, canonical_json

SCHEMA_DIR = Path(__file__).parent / "schema"
MAX_YAML_BYTES = 256 * 1024


class SuiteValidationError(ValueError):
    def __init__(self, message: str, line: int | None = None, column: int | None = None, pointer: str = ""):
        where = f" (line {line}, column {column})" if line else ""
        super().__init__(f"{message}{where}")
        self.message = message
        self.line = line
        self.column = column
        self.pointer = pointer


@cache
def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _node_at(node: yaml.Node | None, path: list[Any]) -> yaml.Node | None:
    for part in path:
        if node is None:
            return None
        if isinstance(node, yaml.MappingNode):
            node = next((v for k, v in node.value if k.value == part), None)
        elif isinstance(node, yaml.SequenceNode) and isinstance(part, int) and part < len(node.value):
            node = node.value[part]
        else:
            return node
    return node


def parse_yaml(text: str) -> tuple[Any, yaml.Node | None]:
    if len(text.encode("utf-8")) > MAX_YAML_BYTES:
        raise SuiteValidationError(f"document exceeds {MAX_YAML_BYTES // 1024} KB")
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text)
    except yaml.MarkedYAMLError as e:
        mark = e.problem_mark
        raise SuiteValidationError(f"YAML syntax error: {e.problem}", mark.line + 1 if mark else None,
                                   mark.column + 1 if mark else None) from None
    return data, node


def _validate(instance: Any, schema_name: str, root: yaml.Node | None, prefix: list[Any]) -> None:
    validator = jsonschema.Draft202012Validator(_schema(schema_name))
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    err = errors[0]
    path = prefix + list(err.absolute_path)
    node = _node_at(root, path)
    pointer = "/" + "/".join(str(p) for p in path)
    line = node.start_mark.line + 1 if node is not None else None
    col = node.start_mark.column + 1 if node is not None else None
    raise SuiteValidationError(f"{pointer or '/'}: {err.message}", line, col, pointer)


@dataclass(frozen=True)
class Suite:
    key: str
    name: str
    document: dict[str, Any]
    version_hash: str

    @property
    def scenarios(self) -> list[dict[str, Any]]:
        return self.document["scenarios"]

    @property
    def personas(self) -> list[dict[str, Any]]:
        return self.document["personas"]

    def scenario(self, key: str) -> dict[str, Any]:
        return next(s for s in self.scenarios if s["key"] == key)

    def persona(self, key: str) -> dict[str, Any]:
        return next(p for p in self.personas if p["key"] == key)


def suite_hash(document: dict[str, Any]) -> str:
    body = {k: v for k, v in document.items() if k != "schema_version"}  # hash covers content, not schema version
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def validate_suite(data: Any, root: yaml.Node | None = None) -> Suite:
    _validate(data, "suite", root, [])
    for i, sc in enumerate(data["scenarios"]):
        _validate(sc, "scenario", root, ["scenarios", i])
    for i, pe in enumerate(data["personas"]):
        _validate(pe, "persona", root, ["personas", i])
    keys = [s["key"] for s in data["scenarios"]]
    if len(keys) != len(set(keys)):
        raise SuiteValidationError("scenario keys must be unique within a suite", pointer="/scenarios")
    pkeys = {p["key"] for p in data["personas"]}
    if len(pkeys) != len(data["personas"]):
        raise SuiteValidationError("persona keys must be unique within a suite", pointer="/personas")
    for i, sc in enumerate(data["scenarios"]):
        if sc.get("persona_key") and sc["persona_key"] not in pkeys:
            node = _node_at(root, ["scenarios", i, "persona_key"])
            raise SuiteValidationError(f"scenario '{sc['key']}' references unknown persona '{sc['persona_key']}'",
                                       node.start_mark.line + 1 if node else None,
                                       node.start_mark.column + 1 if node else None,
                                       f"/scenarios/{i}/persona_key")
        crit = sc.get("success_criteria") or {}
        if crit.get("mode") == "minimum_steps" and crit.get("minimum_steps", 1) > len(sc["goal_checklist"]):
            raise SuiteValidationError(f"scenario '{sc['key']}': minimum_steps exceeds checklist length",
                                       pointer=f"/scenarios/{i}/success_criteria")
    doc = dict(data)
    doc.setdefault("schema_version", 1)
    return Suite(key=doc["key"], name=doc.get("name", doc["key"]), document=doc, version_hash=suite_hash(doc))


def load_suite_text(text: str) -> Suite:
    data, root = parse_yaml(text)
    if not isinstance(data, dict):
        raise SuiteValidationError("suite document must be a mapping", 1, 1)
    return validate_suite(data, root)


def load_condition_profiles(text: str) -> dict[str, dict[str, Any]]:
    """Returns {key: parameters}. Out-of-range values are rejected naming the parameter and range (TC-050)."""
    data, root = parse_yaml(text)
    profiles = (data or {}).get("profiles") or {}
    out: dict[str, dict[str, Any]] = {}
    for key, params in profiles.items():
        try:
            ChaosParams.from_profile(params or {}, strict=True)
        except ConditionError as e:
            node = _node_at(root, ["profiles", key])
            raise SuiteValidationError(f"condition profile '{key}': {e}",
                                       node.start_mark.line + 1 if node else None,
                                       node.start_mark.column + 1 if node else None,
                                       f"/profiles/{key}/{e.parameter}") from None
        out[key] = params or {}
    return out


def load_threshold_profile(text: str) -> ThresholdProfile:
    data, _ = parse_yaml(text)
    try:
        return ThresholdProfile.from_document(data or {})
    except (ProfileError, KeyError, TypeError) as e:
        raise SuiteValidationError(f"threshold profile invalid: {e}") from None


# -- bundled content --------------------------------------------------------------------------------

def bundled_suite(directory: Path = SUITES_DIR) -> Suite:
    scenarios_doc, root = parse_yaml((directory / "booking-core.yaml").read_text(encoding="utf-8"))
    personas_doc, _ = parse_yaml((directory / "personas.yaml").read_text(encoding="utf-8"))
    doc = dict(scenarios_doc)
    doc["personas"] = personas_doc["personas"]
    return validate_suite(doc, None)


def bundled_suite_yaml(directory: Path = SUITES_DIR) -> str:
    suite = bundled_suite(directory)
    return yaml.safe_dump(suite.document, sort_keys=False, allow_unicode=True)


def bundled_conditions(directory: Path = SUITES_DIR) -> dict[str, dict[str, Any]]:
    return load_condition_profiles((directory / "conditions.yaml").read_text(encoding="utf-8"))


def bundled_thresholds(directory: Path = SUITES_DIR) -> ThresholdProfile:
    return load_threshold_profile((directory / "thresholds-default.yaml").read_text(encoding="utf-8"))
