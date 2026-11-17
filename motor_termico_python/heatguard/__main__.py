"""Uso: python -m heatguard examples/base_only.json"""
import argparse
import json
from pathlib import Path

from .pipeline import evaluate


def main():
    parser = argparse.ArgumentParser(description="Procesa un evento térmico HeatGuard")
    parser.add_argument("json_path", type=Path, help="Evento de entrada en JSON")
    args = parser.parse_args()
    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    print(json.dumps(evaluate(payload), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
