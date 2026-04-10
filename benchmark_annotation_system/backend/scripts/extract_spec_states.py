#!/usr/bin/env python3
"""
Extract state and data from Vega/Vega-Lite spec files.

For each spec in specs/, produces:
  - states/{name}.json  (everything except raw data values, with missing fields supplemented)
  - data/{name}.json    (raw data values only)

state + data can be merged back into a fully renderable spec via reconstruct_spec().

Usage:
    python extract_spec_states.py [specs_dir] [--dry-run] [-v]
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_vega_lite(spec: dict) -> bool:
    schema = spec.get("$schema") or ""
    return "vega-lite" in str(schema).lower()


def is_vega(spec: dict) -> bool:
    schema = spec.get("$schema") or ""
    return "vega" in str(schema).lower() and "vega-lite" not in str(schema).lower()


# ---------------------------------------------------------------------------
# Vega-Lite: supplement missing state fields
# ---------------------------------------------------------------------------

def _ensure_scale(channel: dict) -> dict:
    """Add scale: {} to an encoding channel dict if missing."""
    if not isinstance(channel, dict):
        return channel
    if "scale" not in channel:
        return {**channel, "scale": {}}
    return channel


def _supplement_encoding_scales(encoding: dict, channels: tuple = ("x", "y")) -> dict:
    """Add scale: {} to specified encoding channels when missing."""
    if not encoding or not isinstance(encoding, dict):
        return encoding
    out = dict(encoding)
    for ch in channels:
        if ch in out and isinstance(out[ch], dict):
            out[ch] = _ensure_scale(out[ch])
    if "color" in out and isinstance(out["color"], dict) and "scale" not in out["color"]:
        out["color"] = {**out["color"], "scale": {}}
    return out


def supplement_vega_lite_state(state: dict) -> Tuple[dict, List[str]]:
    """
    Supplement a Vega-Lite state dict with missing fields.
    Returns (supplemented_state, list_of_changes).
    """
    changes: List[str] = []
    s = dict(state)

    if "transform" not in s:
        s["transform"] = []
        changes.append("add transform: []")

    if "params" not in s:
        s["params"] = []
        changes.append("add params: []")

    enc = s.get("encoding")
    if enc and isinstance(enc, dict):
        new_enc = _supplement_encoding_scales(enc)
        if new_enc != enc:
            s["encoding"] = new_enc
            changes.append("add encoding channel scale: {} where missing")

    layers = s.get("layer")
    if layers and isinstance(layers, list):
        new_layers = []
        layer_changed = False
        for layer in layers:
            if not isinstance(layer, dict):
                new_layers.append(layer)
                continue
            le = layer.get("encoding")
            if le and isinstance(le, dict):
                new_le = _supplement_encoding_scales(le)
                if new_le != le:
                    new_layers.append({**layer, "encoding": new_le})
                    layer_changed = True
                else:
                    new_layers.append(layer)
            else:
                new_layers.append(layer)
        if layer_changed:
            s["layer"] = new_layers
            changes.append("add layer[].encoding channel scale: {} where missing")

    return s, changes


# ---------------------------------------------------------------------------
# Vega-Lite: split spec -> (state, data)
# ---------------------------------------------------------------------------

def split_vega_lite(spec: dict) -> Tuple[dict, dict]:
    """
    Split a Vega-Lite spec into state and data.

    State = everything except spec["data"]
    Data  = spec["data"]  (typically {"values": [...]})
    """
    state = {k: v for k, v in spec.items() if k != "data"}
    data = spec.get("data", {})
    return state, data


# ---------------------------------------------------------------------------
# Vega: split spec -> (state, data)
# ---------------------------------------------------------------------------

def _is_source_data_entry(entry: dict) -> bool:
    """A source data entry has 'values' and no 'source' key."""
    return isinstance(entry, dict) and "values" in entry and "source" not in entry


def split_vega(spec: dict) -> Tuple[dict, dict]:
    """
    Split a Vega spec into state and data.

    State = full spec, but source data entries have values replaced by []
    Data  = { <name>: <values>, ... } for each source data entry
    """
    data_out: Dict[str, Any] = {}
    state = copy.deepcopy(spec)

    data_array = state.get("data", [])
    if isinstance(data_array, list):
        for entry in data_array:
            if _is_source_data_entry(entry):
                name = entry.get("name", "")
                data_out[name] = entry["values"]
                entry["values"] = []

    return state, data_out


# ---------------------------------------------------------------------------
# Reconstruction: state + data -> renderable spec
# ---------------------------------------------------------------------------

def reconstruct_spec(state: dict, data: dict) -> dict:
    """
    Reconstruct a renderable spec from state + data.

    For Vega-Lite: spec = {**state, "data": data}
    For Vega:      fill source data entries' values from data dict
    """
    if is_vega_lite(state):
        return {**state, "data": data}
    else:
        spec = copy.deepcopy(state)
        data_array = spec.get("data", [])
        if isinstance(data_array, list):
            for entry in data_array:
                if isinstance(entry, dict) and "name" in entry:
                    name = entry["name"]
                    if name in data and entry.get("values") == []:
                        entry["values"] = data[name]
        return spec


# ---------------------------------------------------------------------------
# Main extraction logic
# ---------------------------------------------------------------------------

def extract_one(spec: dict, verbose: bool = False) -> Tuple[dict, dict, List[str]]:
    """
    Extract state and data from a single spec.
    Returns (state, data, changes).
    """
    changes: List[str] = []

    if is_vega_lite(spec):
        state, data = split_vega_lite(spec)
        state, suppl_changes = supplement_vega_lite_state(state)
        changes.extend(suppl_changes)
        changes.insert(0, "vega-lite")
    elif is_vega(spec):
        state, data = split_vega(spec)
        changes.insert(0, "vega")
    else:
        state, data = split_vega_lite(spec)
        state, suppl_changes = supplement_vega_lite_state(state)
        changes.extend(suppl_changes)
        changes.insert(0, "unknown-schema (treated as vega-lite)")

    return state, data, changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract state and data from Vega/Vega-Lite specs."
    )
    parser.add_argument(
        "specs_dir",
        nargs="?",
        default=None,
        help="Directory containing JSON specs (default: backend/specs relative to this script)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be done.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    base = script_dir.parent  # backend/
    specs_dir = Path(args.specs_dir) if args.specs_dir else base / "specs"
    states_dir = base / "states"
    data_dir = base / "data"

    if not specs_dir.is_dir():
        print(f"Error: not a directory: {specs_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        states_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(specs_dir.glob("*.json"))
    processed = 0
    skipped = 0

    for path in json_files:
        try:
            text = path.read_text(encoding="utf-8")
            spec = json.loads(text)
        except Exception as e:
            if args.verbose:
                print(f"  SKIP {path.name}: {e}")
            skipped += 1
            continue

        if not isinstance(spec, dict):
            if args.verbose:
                print(f"  SKIP {path.name}: top-level is not an object")
            skipped += 1
            continue

        state, data, changes = extract_one(spec, verbose=args.verbose)

        state_path = states_dir / path.name
        data_path = data_dir / path.name

        if args.verbose or args.dry_run:
            print(f"  {path.name}: {', '.join(changes)}")

        if not args.dry_run:
            state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            data_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        processed += 1

    action = "Would process" if args.dry_run else "Processed"
    print(f"\n{action} {processed} spec(s), skipped {skipped}.")
    if args.dry_run:
        print("(dry-run: no files written)")
    else:
        print(f"  States -> {states_dir}")
        print(f"  Data   -> {data_dir}")


if __name__ == "__main__":
    main()
