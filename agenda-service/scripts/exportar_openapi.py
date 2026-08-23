"""Exporta o contrato OpenAPI como artefato versionado (RF-17).

Uso: uv run python scripts/exportar_openapi.py [destino]
Padrão: ../docs/openapi.json (raiz do repo). O teste test_contrato garante
que o artefato não fica defasado em relação ao código.
"""

import json
import os
import sys
from pathlib import Path

# O import de app.main lê settings — nenhum segredo é necessário para gerar o schema.
os.environ.setdefault("APP_ENV", "dev")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def exportar(destino: Path) -> None:
    spec = app.openapi()
    destino.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rotas = sum(len(ops) for ops in spec["paths"].values())
    print(f"{destino}: {rotas} operações, versão {spec['info']['version']}")


if __name__ == "__main__":
    padrao = Path(__file__).resolve().parent.parent.parent / "docs" / "openapi.json"
    exportar(Path(sys.argv[1]) if len(sys.argv) > 1 else padrao)
