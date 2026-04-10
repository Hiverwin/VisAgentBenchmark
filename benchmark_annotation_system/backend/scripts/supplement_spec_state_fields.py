#!/usr/bin/env python3
"""
Supplement Vega-Lite specs with the four state fields when missing:
- transform: [] (Data Transformation)
- params: [] (Interactive Selection)
- encoding.x.scale: {}, encoding.y.scale: {} (View Transformation)

Only processes files where $schema contains "vega-lite". Skips Vega (e.g. Sankey) specs.
"""

import argparse
import json
import sys
from pathlib import Path


def is_vega_lite(spec: dict) -> bool:
    schema = spec.get("$schema") or ""
    return "vega-lite" in str(schema).lower()


def ensure_scale_on_channel(channel: dict) -> dict:
    """If channel is a dict and has no 'scale', add scale: {}."""
    if not isinstance(channel, dict):
        return channel
    if "scale" not in channel:
        return {**channel, "scale": {}}
    return channel


def add_scale_to_encoding(encoding: dict, view_channels: tuple = ("x", "y")) -> dict:
    """Add scale: {} to encoding.x and encoding.y when missing."""
    if not encoding or not isinstance(encoding, dict):
        return encoding
    out = dict(encoding)
    for key in view_channels:
        if key in out:
            out[key] = ensure_scale_on_channel(out[key])
    return out


def supplement_spec(spec: dict, verbose: bool = False) -> tuple[dict, list[str]]:
    """
    Supplement one spec with missing state fields.
    Returns (modified_spec, list of change descriptions).
    """
    changes = []

    if not is_vega_lite(spec):
        return spec, []

    # 1. transform
    if "transform" not in spec:
        spec = {**spec, "transform": []}
        changes.append("add transform: []")

    # 2. params
    if "params" not in spec:
        spec = {**spec, "params": []}
        changes.append("add params: []")

    # 3. encoding.*.scale (top-level encoding)
    enc = spec.get("encoding")
    if enc and isinstance(enc, dict):
        new_enc = add_scale_to_encoding(enc)
        if new_enc != enc:
            spec = {**spec, "encoding": new_enc}
            changes.append("add encoding.x/y scale: {} where missing")

    # 4. layer[].encoding.*.scale
    layers = spec.get("layer")
    if layers and isinstance(layers, list):
        new_layers = []
        layer_changed = False
        for layer in layers:
            if not isinstance(layer, dict):
                new_layers.append(layer)
                continue
            le = layer.get("encoding")
            if le and isinstance(le, dict):
                new_le = add_scale_to_encoding(le)
                if new_le != le:
                    new_layers.append({**layer, "encoding": new_le})
                    layer_changed = True
                else:
                    new_layers.append(layer)
            else:
                new_layers.append(layer)
        if layer_changed:
            spec = {**spec, "layer": new_layers}
            changes.append("add layer[].encoding x/y scale: {} where missing")

    return spec, changes


def main():
    parser = argparse.ArgumentParser(description="Supplement Vega-Lite specs with state fields.")
    parser.add_argument(
        "specs_dir",
        nargs="?",
        default=None,
        help="Directory containing JSON specs (default: backend/specs relative to this script)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be changed.")
    parser.add_argument("-v", "--verbose", action="store_true", help="List each file and changes.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    base = script_dir.parent  # backend
    specs_dir = Path(args.specs_dir) if args.specs_dir else base / "specs"
    if not specs_dir.is_dir():
        print(f"Error: not a directory: {specs_dir}", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(specs_dir.glob("*.json"))
    modified_count = 0
    skipped_count = 0

    for path in json_files:
        try:
            text = path.read_text(encoding="utf-8")
            spec = json.loads(text)
        except Exception as e:
            if args.verbose:
                print(f"Skip {path.name}: {e}")
            skipped_count += 1
            continue

        if not is_vega_lite(spec):
            if args.verbose:
                print(f"Skip {path.name}: not Vega-Lite")
            skipped_count += 1
            continue

        new_spec, changes = supplement_spec(spec, verbose=args.verbose)
        if not changes:
            continue

        modified_count += 1
        if args.verbose:
            print(f"{path.name}: {', '.join(changes)}")

        if args.dry_run:
            continue

        out_text = json.dumps(new_spec, indent=2, ensure_ascii=False)
        path.write_text(out_text, encoding="utf-8")

    print(f"Done. Modified {modified_count} Vega-Lite spec(s), skipped {skipped_count} file(s).")
    if args.dry_run and modified_count:
        print("(dry-run: no files written)")


if __name__ == "__main__":
    main()
