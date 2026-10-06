"""Importa produtos do CATALOGO.csv (mantido pelo Cláudio/Thiago) para o app financeiro.

Assim, todo tênis/bolsa que já foi cadastrado pro site já aparece aqui também,
sem digitar de novo. Re-executar é seguro: atualiza o que já existe (por CODIGO),
sem duplicar. O preço de custo NUNCA vem do CSV (ele não tem essa coluna) — é
preenchido à mão dentro do app e o import nunca apaga o que já foi preenchido.

No PC, o botão "Atualizar do catálogo" lê direto do drive de rede (CATALOGO_PATH).
Na nuvem esse drive não existe, então a tela oferece upload manual do arquivo —
mesma função, só troca de onde o texto do CSV vem (`processar_conteudo`).
"""
import csv
import io
import shutil
from pathlib import Path
from datetime import date, datetime

import db

CATALOGO_PATH = Path(__file__).parent.parent / "Catalogo-Produtos" / "CATALOGO.csv"


def _preco(valor: str):
    if not valor:
        return None
    limpo = valor.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


PREFIXO_MANUAL = "MANUAL"   # produtos cadastrados à mão no app: nunca vêm do CSV, nunca são removidos
MIN_LINHAS_ESPELHO = 100     # CSV com menos linhas que isso não autoriza remover nada (arquivo truncado)
MAX_FRACAO_REMOCAO = 0.5     # nunca remove mais da metade da lista de uma vez


def _espelhar(conn, codigos_csv: set) -> dict:
    """Deixa a tabela produtos igual ao CATALOGO.csv: remove o que não está mais nele.

    Pedido do Thiago (05/10/2026): a lista do financeiro tem que ser igual à do site.
    Antes de apagar, copia o banco inteiro e exporta as linhas removidas (com o preço
    de custo preenchido à mão) para backups\\, então nada se perde."""
    if len(codigos_csv) < MIN_LINHAS_ESPELHO:
        return {"removidos": [], "espelho": f"ignorado: CSV com só {len(codigos_csv)} produtos"}
    linhas = conn.execute(
        "SELECT * FROM produtos WHERE codigo NOT LIKE ?", (f"{PREFIXO_MANUAL}%",)
    ).fetchall()
    sobram = [r for r in linhas if r["codigo"] not in codigos_csv]
    if not sobram:
        return {"removidos": []}
    if len(sobram) > MAX_FRACAO_REMOCAO * len(linhas):
        return {"removidos": [],
                "espelho": f"recusado: removeria {len(sobram)} de {len(linhas)} produtos, confira o CSV"}

    pasta = Path(db.DB_PATH).parent / "backups"
    pasta.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M")
    conn.commit()
    shutil.copyfile(db.DB_PATH, pasta / f"dados_antes_espelho_{carimbo}.db")
    colunas = linhas[0].keys()
    with open(pasta / f"produtos_removidos_{carimbo}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(colunas)
        for r in sobram:
            w.writerow([r[c] for c in colunas])
    conn.executemany("DELETE FROM produtos WHERE codigo = ?", [(r["codigo"],) for r in sobram])
    conn.commit()
    return {"removidos": sorted(r["codigo"] for r in sobram)}


def processar_conteudo(texto_csv: str, espelhar: bool = False) -> dict:
    """Recebe o texto do CSV (de onde vier — arquivo local ou upload) e importa.

    Com espelhar=True também remove da tabela o que não está mais no CSV (ver _espelhar)."""
    conn = db.get_conn()
    total = 0
    codigos_csv = set()
    # O CSV sai do Excel com BOM. Se ele sobrar, a primeira coluna vira "﻿CODIGO"
    # e NENHUMA linha importa — some tudo em silêncio, sem erro. Tira aqui pra valer
    # pros dois caminhos (upload pela tela e envio pelo deploy).
    texto_csv = texto_csv.lstrip("﻿")
    leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=";", quotechar='"')
    hoje = date.today().isoformat()
    for linha in leitor:
        codigo = (linha.get("CODIGO") or "").strip()
        nome = (linha.get("NOME") or "").strip()
        if not codigo or not nome:
            continue
        codigos_csv.add(codigo)
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
    resultado = {"ok": True, "total": total}
    if espelhar:
        resultado.update(_espelhar(conn, codigos_csv))
    conn.close()
    return resultado


def importar():
    """Lê direto do Q:\\ — só funciona rodando no PC do Thiago, não na nuvem.
    Espelha: o que saiu do CATALOGO.csv sai também do financeiro."""
    if not CATALOGO_PATH.exists():
        return {"ok": False, "erro": f"Não encontrei {CATALOGO_PATH}"}
    with open(CATALOGO_PATH, encoding="utf-8-sig", newline="") as f:
        return processar_conteudo(f.read(), espelhar=True)


if __name__ == "__main__":
    resultado = importar()
    if resultado["ok"]:
        print(f"{resultado['total']} produtos importados/atualizados de {CATALOGO_PATH.name}.")
        if resultado.get("removidos"):
            print(f"{len(resultado['removidos'])} removidos (não estão mais no catálogo): {', '.join(resultado['removidos'])}")
        if resultado.get("espelho"):
            print(f"Espelhamento: {resultado['espelho']}")
    else:
        print(f"Erro: {resultado['erro']}")
