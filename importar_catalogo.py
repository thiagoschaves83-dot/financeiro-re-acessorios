"""Importa produtos do CATALOGO.csv (mantido pelo Cláudio/Thiago) para o app financeiro.

Assim, todo tênis/bolsa que já foi cadastrado pro site já aparece aqui também,
sem digitar de novo. Re-executar é seguro: atualiza o que já existe (por CODIGO),
sem duplicar. O preço de custo NUNCA vem do CSV (ele não tem essa coluna) — é
preenchido à mão dentro do app e o import nunca apaga o que já foi preenchido.

No PC, o botão "Atualizar do catálogo" lê direto do Q:\ (CATALOGO_PATH). Na nuvem
não existe Q:\, então a tela oferece upload manual do arquivo — mesma função,
só troca de onde o texto do CSV vem (`processar_conteudo`).
"""
import csv
import io
from pathlib import Path
from datetime import date

import db

CATALOGO_PATH = Path(__file__).parent.parent / "CATALOGO.csv"


def _preco(valor: str):
    if not valor:
        return None
    limpo = valor.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def processar_conteudo(texto_csv: str) -> dict:
    """Recebe o texto do CSV (de onde vier — arquivo local ou upload) e importa."""
    conn = db.get_conn()
    total = 0
    leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=";", quotechar='"')
    hoje = date.today().isoformat()
    for linha in leitor:
        codigo = (linha.get("CODIGO") or "").strip()
        nome = (linha.get("NOME") or "").strip()
        if not codigo or not nome:
            continue
        db.upsert_produto(
            conn,
            {
                "codigo": codigo,
                "id_origem": (linha.get("ID") or "").strip(),
                "nome": nome,
                "marca": (linha.get("MARCA") or "").strip(),
                "tipo": (linha.get("TIPO") or "").strip(),
                "genero": (linha.get("GENERO") or "").strip(),
                "categoria": (linha.get("CATEGORIA") or "").strip(),
                "numeracao": (linha.get("NUMERACAO") or "").strip(),
                "preco_venda": _preco(linha.get("PRECO")),
                "preco_custo": None,
                "linha": (linha.get("LINHA") or "").strip(),
                "status_catalogo": (linha.get("STATUS") or "").strip(),
                "atualizado_em": hoje,
            },
        )
        total += 1
    conn.commit()
    conn.close()
    return {"ok": True, "total": total}


def importar():
    """Lê direto do Q:\\ — só funciona rodando no PC do Thiago, não na nuvem."""
    if not CATALOGO_PATH.exists():
        return {"ok": False, "erro": f"Não encontrei {CATALOGO_PATH}"}
    with open(CATALOGO_PATH, encoding="utf-8-sig", newline="") as f:
        return processar_conteudo(f.read())


if __name__ == "__main__":
    resultado = importar()
    if resultado["ok"]:
        print(f"{resultado['total']} produtos importados/atualizados de {CATALOGO_PATH.name}.")
    else:
        print(f"Erro: {resultado['erro']}")
