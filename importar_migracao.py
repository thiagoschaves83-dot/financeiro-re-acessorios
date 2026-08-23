# -*- coding: utf-8 -*-
"""Importa compras/parcelas/pagamentos históricos de um JSON pré-processado
(vindo da planilha 'Atualização do financeiro.xlsx') para o banco do app.

Uso: python importar_migracao.py <caminho_do_dados.db> <caminho_do_json>

O JSON esperado é uma lista de compras, cada uma:
{
  "cliente_nome": "...", "cliente_telefone": "... ou null",
  "data": "AAAA-MM-DD",
  "itens": [{"descricao": "...", "qtd": 1}, ...],
  "valor_total": 700.0,
  "parcelas_pagas": [["AAAA-MM-DD", 120.0], ...],
  "parcelas_abertas": [["AAAA-MM-DD", 140.0], ...]
}

Cada compra recebe um código sequencial [MIGR-NNN] na frente da descrição,
pra ficar claro que veio da importação e não do cadastro normal (produtos
dessa planilha antiga podem ter descrição divergente do catálogo atual).
"""
import json
import sqlite3
import sys

PREFIXO = "MIGR"


def importar(db_path, json_path):
    with open(json_path, encoding="utf-8") as f:
        compras = json.load(f)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    clientes_cache = {}
    resumo = []

    for i, cp in enumerate(compras, 1):
        chave = (cp["cliente_nome"].strip().lower(), cp.get("cliente_telefone"))
        if chave not in clientes_cache:
            cur = conn.execute(
                "INSERT INTO clientes (nome, telefone, criado_em) VALUES (?, ?, ?)",
                (cp["cliente_nome"].strip(), cp.get("cliente_telefone") or "", cp["data"]),
            )
            clientes_cache[chave] = cur.lastrowid
        cliente_id = clientes_cache[chave]

        codigo = f"[{PREFIXO}-{i:03d}]"
        itens_txt = "; ".join(
            (it["descricao"] or "Produto não identificado")
            + (f" ({it['qtd']}x)" if it.get("qtd") and it["qtd"] > 1 else "")
            for it in cp["itens"]
        )
        descricao = f"{codigo} {itens_txt}"

        cur = conn.execute(
            "INSERT INTO compras (cliente_id, descricao, valor_total, data) VALUES (?, ?, ?, ?)",
            (cliente_id, descricao, cp["valor_total"], cp["data"]),
        )
        compra_id = cur.lastrowid

        parcelas = [(venc, valor, True) for venc, valor in cp.get("parcelas_pagas", [])]
        parcelas += [(venc, valor, False) for venc, valor in cp.get("parcelas_abertas", [])]
        parcelas.sort(key=lambda x: x[0])

        for numero, (venc, valor, paga) in enumerate(parcelas, 1):
            pcur = conn.execute(
                "INSERT INTO parcelas (compra_id, numero, valor_previsto, vencimento) VALUES (?, ?, ?, ?)",
                (compra_id, numero, valor, venc),
            )
            if paga:
                conn.execute(
                    "INSERT INTO pagamentos (compra_id, parcela_id, valor, data, forma_pagamento) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (compra_id, pcur.lastrowid, valor, venc, "Importado (planilha antiga)"),
                )

        pago_total = sum(v for _, v, p in parcelas if p)
        resumo.append((codigo, cp["cliente_nome"], cp["valor_total"], pago_total, cp["valor_total"] - pago_total))

    conn.commit()
    conn.close()
    return resumo, len(clientes_cache)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python importar_migracao.py <dados.db> <json>")
        sys.exit(1)
    resumo, n_clientes = importar(sys.argv[1], sys.argv[2])
    print(f"Clientes criados: {n_clientes}")
    print(f"Compras criadas: {len(resumo)}")
    total_v = sum(r[2] for r in resumo)
    total_p = sum(r[3] for r in resumo)
    total_s = sum(r[4] for r in resumo)
    print(f"Total vendido: R$ {total_v:.2f} | Pago: R$ {total_p:.2f} | Em aberto: R$ {total_s:.2f}")
