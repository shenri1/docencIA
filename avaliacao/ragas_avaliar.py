"""Avaliação offline com RAGAS — Núcleo Semântico, fora de `backend/app/`.

Mede ancoragem (faithfulness) e ordem dos trechos (context precision) de um
banco já gerado. Não mede qualidade pedagógica. 

    uv run --project avaliacao python -m avaliacao.ragas_avaliar --sessao 12 --limite 5

Os nomes da API do RAGAS abaixo seguem a 0.4.3 e NÃO foram executados: rode
primeiro com --limite 5 e confira quantas linhas voltam NaN.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from avaliacao.amostras import montar_amostras
from avaliacao.carregar import carregar_da_sessao

TEMPERATURA = 0.0


def _url_do_banco() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Defina DATABASE_URL (pode ser a mesma do .env).")
    # A do .env vem no formato do SQLAlchemy e com o host do Compose ("db"), que
    # só resolve dentro dos containers: a mesma troca do dev.py e do alembic.
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "@db:", "@localhost:"
    )


def _avaliar(amostras: list[dict], modelo: str, base_url: str):
    from langchain_ollama import ChatOllama
    from ragas import EvaluationDataset, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

    juiz = LangchainLLMWrapper(
        ChatOllama(model=modelo, base_url=base_url, temperature=TEMPERATURA)
    )
    return evaluate(
        EvaluationDataset.from_list(amostras),
        metrics=[
            Faithfulness(llm=juiz),
            LLMContextPrecisionWithoutReference(llm=juiz),
        ],
    )


def _nan(valor) -> bool:
    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sessao", type=int, required=True)
    ap.add_argument("--limite", type=int, help="avalia só as N primeiras (piloto)")
    ap.add_argument("--juiz", default="qwen3.5:9b")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--saida", type=Path, default=Path("avaliacao/resultados"))
    args = ap.parse_args()

    questoes = carregar_da_sessao(_url_do_banco(), args.sessao)
    montagem = montar_amostras(questoes)
    if args.limite:
        montagem.amostras = montagem.amostras[: args.limite]
        montagem.ids = montagem.ids[: args.limite]

    quadro = _avaliar(montagem.amostras, args.juiz, args.base_url).to_pandas()
    quadro.insert(0, "questao_id", montagem.ids)

    metricas = [c for c in ("faithfulness", "llm_context_precision_without_reference")
                if c in quadro.columns]
    carimbo = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    args.saida.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(args.saida / f"rodada_{carimbo}.csv", index=False)

    resumo = {
        "data": carimbo,
        "sessao": args.sessao,
        "ragas": version("ragas"),
        "juiz": args.juiz,
        "temperatura": TEMPERATURA,
        "modo_contextos": "1 (trechos citados pela questão)",
        "avaliadas": len(montagem.ids),
        "puladas": montagem.puladas,
        "metricas": {
            m: {
                "nan": int(sum(_nan(v) for v in quadro[m])),
                "media": float(quadro[m].mean()),
            }
            for m in metricas
        },
    }
    (args.saida / f"rodada_{carimbo}.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
