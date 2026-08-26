"""Banco de dados do app financeiro da Rê Acessórios — SQLite em arquivo único."""
import re
import sqlite3
import unicodedata
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent / "dados.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    descricao TEXT NOT NULL,
    valor_total REAL NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parcelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    numero INTEGER NOT NULL,
    valor_previsto REAL NOT NULL,
    vencimento TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    parcela_id INTEGER REFERENCES parcelas(id),
    valor REAL NOT NULL,
    data TEXT NOT NULL,
    forma_pagamento TEXT
);

CREATE TABLE IF NOT EXISTS historico_edicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    campo TEXT NOT NULL,
    valor_antigo TEXT,
    valor_novo TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS produtos (
    codigo TEXT PRIMARY KEY,
    id_origem TEXT,
    nome TEXT NOT NULL,
    marca TEXT,
    tipo TEXT,
    genero TEXT,
    categoria TEXT,
    numeracao TEXT,
    preco_venda REAL,
    preco_custo REAL,
    linha TEXT,
    status_catalogo TEXT,
    atualizado_em TEXT NOT NULL
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def hoje():
    return date.today().isoformat()


# ---------- Clientes ----------

def listar_clientes(conn, busca=None):
    """Sem `busca`, lista todo mundo. Com `busca`, filtra por trecho do nome —
    ignorando acento e caixa (mesma normalização usada na checagem de duplicidade),
    porque digitar "Cecilia" tem que achar "Maria Cecília" mesmo sem acento e sem
    ser o nome inteiro."""
    linhas = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    if not busca:
        return linhas
    termo = _normalizar_texto(busca)
    return [c for c in linhas if termo in _normalizar_texto(c["nome"])]


def buscar_cliente(conn, cliente_id):
    return conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()


def buscar_cliente_por_nome(conn, nome):
    """Match exato (ignorando maiúsculas/espaço nas pontas) — usado pra decidir
    se a 'Nova venda' reaproveita um cliente já cadastrado ou cria um novo."""
    nome_normalizado = nome.strip().lower()
    for c in conn.execute("SELECT * FROM clientes").fetchall():
        if c["nome"].strip().lower() == nome_normalizado:
            return c
    return None


def criar_cliente(conn, nome, telefone):
    cur = conn.execute(
        "INSERT INTO clientes (nome, telefone, criado_em) VALUES (?, ?, ?)",
        (nome.strip(), telefone.strip(), hoje()),
    )
    conn.commit()
    return cur.lastrowid


def editar_cliente(conn, cliente_id, nome, telefone):
    """Corrige nome/telefone a qualquer momento (ex.: erro de digitação ou dado
    importado errado) — sem histórico, porque historico_edicoes é amarrado a
    compra_id, não a cliente_id."""
    conn.execute(
        "UPDATE clientes SET nome = ?, telefone = ? WHERE id = ?",
        (nome.strip(), (telefone or "").strip(), cliente_id),
    )
    conn.commit()


def _normalizar_texto(texto):
    """Minúsculo, sem acento, sem espaço duplicado — usada tanto pra nome de cliente
    quanto pra nome/código/marca de produto, pra comparar sem que 'É' vs 'e' ou
    espaço a mais atrapalhe o match (busca e checagem de duplicidade usam a mesma
    definição de 'parecido')."""
    texto = (texto or "").strip().lower()
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def _distancia_edicao(a, b):
    """Levenshtein simples (sem biblioteca externa) — usado só pra pegar variação
    pequena de grafia (ex.: 'Vanda Baldutti' x 'Vanda Balduti')."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            custo = 0 if ca == cb else 1
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo))
        anterior = atual
    return anterior[-1]


def _nomes_parecidos(nome_a_norm, nome_b_norm):
    """True se forem quase o mesmo nome (pequena variação de grafia) mas não
    idênticos depois de normalizado. Tolerância proporcional ao tamanho do nome —
    não precisa ser perfeito, só pegar os casos mais comuns de digitação."""
    if not nome_a_norm or not nome_b_norm or nome_a_norm == nome_b_norm:
        return False
    distancia = _distancia_edicao(nome_a_norm, nome_b_norm)
    tolerancia = max(1, round(max(len(nome_a_norm), len(nome_b_norm)) * 0.15))
    return distancia <= tolerancia


def buscar_clientes_duplicados(conn, nome, telefone):
    """Usado só pro aviso (não bloqueante) de possível duplicidade no cadastro.
    Telefone igual (comparando só os dígitos) é sinal forte de ser a mesma pessoa —
    marca gravidade 'forte'. Nome igual ou parecido (variação de grafia) é sinal
    mais fraco — marca 'branda'. Cada resultado já vem com saldo em aberto e última
    compra, pra ajudar o Thiago a decidir se é a mesma pessoa ou coincidência."""
    nome_norm = _normalizar_texto(nome)
    tel_digitos = re.sub(r"\D", "", telefone or "")
    resultado = []
    for c in conn.execute("SELECT * FROM clientes").fetchall():
        c_nome_norm = _normalizar_texto(c["nome"])
        c_tel_digitos = re.sub(r"\D", "", c["telefone"] or "")

        bate_telefone = bool(tel_digitos) and tel_digitos == c_tel_digitos
        nome_identico = bool(nome_norm) and nome_norm == c_nome_norm
        nome_parecido = bool(nome_norm) and not nome_identico and _nomes_parecidos(nome_norm, c_nome_norm)

        if not (bate_telefone or nome_identico or nome_parecido):
            continue

        if bate_telefone:
            motivo = "telefone"
        elif nome_identico:
            motivo = "nome_identico"
        else:
            motivo = "nome_parecido"

        compras = listar_compras_cliente(conn, c["id"])
        saldo_total = round(sum(x["saldo"] for x in compras if x["saldo"] > 0), 2)
        ultima_compra = max((x["data"] for x in compras), default=None)

        resultado.append({
            "id": c["id"],
            "nome": c["nome"],
            "telefone": c["telefone"],
            "saldo_total": saldo_total,
            "ultima_compra": ultima_compra,
            "motivo": motivo,
            "gravidade": "forte" if bate_telefone else "branda",
        })
    resultado.sort(key=lambda r: 0 if r["gravidade"] == "forte" else 1)
    return resultado


# ---------- Compras ----------

def saldo_compra(conn, compra):
    pago = conn.execute(
        "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE compra_id = ?",
        (compra["id"],),
    ).fetchone()["total"]
    return round(compra["valor_total"] - pago, 2), round(pago, 2)


def listar_compras_cliente(conn, cliente_id):
    compras = conn.execute(
        "SELECT * FROM compras WHERE cliente_id = ? ORDER BY data DESC, id DESC",
        (cliente_id,),
    ).fetchall()
    resultado = []
    for c in compras:
        saldo, pago = saldo_compra(conn, c)
        resultado.append({**dict(c), "saldo": saldo, "pago": pago})
    return resultado


def buscar_compra(conn, compra_id):
    return conn.execute("SELECT * FROM compras WHERE id = ?", (compra_id,)).fetchone()


def criar_compra(conn, cliente_id, descricao, valor_total, datas_parcelas, entrada=0):
    """datas_parcelas: uma data (AAAA-MM-DD) por parcela, na ordem — cada uma já vem
    editada da tela se o Thiago mudou o padrão de 30 em 30 dias. Lista vazia = à vista,
    sem parcela fixa. `entrada`: valor já pago na hora da venda — vira um pagamento
    imediato, e as parcelas dividem só o que sobra (valor_total - entrada), não o
    valor_total inteiro."""
    cur = conn.execute(
        "INSERT INTO compras (cliente_id, descricao, valor_total, data) VALUES (?, ?, ?, ?)",
        (cliente_id, descricao.strip(), valor_total, hoje()),
    )
    compra_id = cur.lastrowid
    entrada = entrada or 0
    if entrada > 0:
        conn.execute(
            "INSERT INTO pagamentos (compra_id, parcela_id, valor, data, forma_pagamento) VALUES (?, ?, ?, ?, ?)",
            (compra_id, None, entrada, hoje(), "Entrada"),
        )
    datas_parcelas = [d for d in datas_parcelas if d]
    if datas_parcelas:
        restante = round(valor_total - entrada, 2)
        valor_parcela = round(restante / len(datas_parcelas), 2)
        for i, venc in enumerate(datas_parcelas):
            conn.execute(
                "INSERT INTO parcelas (compra_id, numero, valor_previsto, vencimento) VALUES (?, ?, ?, ?)",
                (compra_id, i + 1, valor_parcela, venc),
            )
    conn.commit()
    return compra_id


def editar_compra(conn, compra_id, novo_valor, nova_descricao):
    """Edita valor e/ou descrição (produto) da compra a qualquer momento, mesmo com
    pagamento já registrado. Nunca bloqueia — só registra cada mudança no histórico."""
    compra = buscar_compra(conn, compra_id)
    nova_descricao = (nova_descricao or "").strip()
    mudancas = []
    if str(compra["valor_total"]) != str(novo_valor):
        mudancas.append(("valor_total", compra["valor_total"], novo_valor))
    if (compra["descricao"] or "") != nova_descricao:
        mudancas.append(("descricao", compra["descricao"], nova_descricao))

    conn.execute(
        "UPDATE compras SET valor_total = ?, descricao = ? WHERE id = ?",
        (novo_valor, nova_descricao, compra_id),
    )
    for campo, antigo, novo in mudancas:
        conn.execute(
            "INSERT INTO historico_edicoes (compra_id, campo, valor_antigo, valor_novo, data) VALUES (?, ?, ?, ?, ?)",
            (compra_id, campo, str(antigo), str(novo), hoje()),
        )
    conn.commit()


def editar_parcela(conn, parcela_id, novo_vencimento, novo_valor_previsto):
    """Corrige a data de vencimento e/ou valor previsto de uma parcela ainda não paga
    (ex.: Thiago combinou um novo prazo com o cliente). Registra no histórico da compra,
    igual às outras edições — nunca bloqueia."""
    parcela = conn.execute("SELECT * FROM parcelas WHERE id = ?", (parcela_id,)).fetchone()
    if not parcela:
        return
    mudancas = []
    if parcela["vencimento"] != novo_vencimento:
        mudancas.append(("parcela_vencimento", parcela["vencimento"], novo_vencimento))
    if str(parcela["valor_previsto"]) != str(novo_valor_previsto):
        mudancas.append(("parcela_valor_previsto", parcela["valor_previsto"], novo_valor_previsto))
    if not mudancas:
        return
    conn.execute(
        "UPDATE parcelas SET vencimento = ?, valor_previsto = ? WHERE id = ?",
        (novo_vencimento, novo_valor_previsto, parcela_id),
    )
    for campo, antigo, novo in mudancas:
        conn.execute(
            "INSERT INTO historico_edicoes (compra_id, campo, valor_antigo, valor_novo, data) VALUES (?, ?, ?, ?, ?)",
            (parcela["compra_id"], campo, str(antigo), str(novo), hoje()),
        )
    conn.commit()


def excluir_compra(conn, compra_id):
    """Exclui a compra inteira e tudo que pertence só a ela (parcelas, histórico de
    edição, e qualquer pagamento remanescente). Quem chama já garantiu que não tem
    pagamento de verdade registrado — a exclusão de pagamentos aqui é só rede de
    segurança pra não sobrar nada órfão."""
    conn.execute("DELETE FROM pagamentos WHERE compra_id = ?", (compra_id,))
    conn.execute("DELETE FROM parcelas WHERE compra_id = ?", (compra_id,))
    conn.execute("DELETE FROM historico_edicoes WHERE compra_id = ?", (compra_id,))
    conn.execute("DELETE FROM compras WHERE id = ?", (compra_id,))
    conn.commit()


def historico_compra(conn, compra_id):
    return conn.execute(
        "SELECT * FROM historico_edicoes WHERE compra_id = ? ORDER BY id DESC", (compra_id,)
    ).fetchall()


def parcelas_compra(conn, compra_id):
    return conn.execute(
        "SELECT * FROM parcelas WHERE compra_id = ? ORDER BY numero", (compra_id,)
    ).fetchall()


# ---------- Pagamentos ----------

def registrar_pagamento(conn, compra_id, valor, forma_pagamento, parcela_id=None):
    cur = conn.execute(
        "INSERT INTO pagamentos (compra_id, parcela_id, valor, data, forma_pagamento) VALUES (?, ?, ?, ?, ?)",
        (compra_id, parcela_id, valor, hoje(), forma_pagamento),
    )
    conn.commit()
    return cur.lastrowid


def buscar_pagamento(conn, pagamento_id):
    return conn.execute("SELECT * FROM pagamentos WHERE id = ?", (pagamento_id,)).fetchone()


def pagamentos_compra(conn, compra_id):
    return conn.execute(
        "SELECT * FROM pagamentos WHERE compra_id = ? ORDER BY id DESC", (compra_id,)
    ).fetchall()


def editar_pagamento(conn, pagamento_id, novo_valor, nova_data, nova_forma_pagamento):
    """Edita um pagamento já registrado — inclusive a data (ex.: baixa lançada dia 13,
    mas o Pix caiu dia 10; corrige aqui pra não gerar atraso indevido). Nunca bloqueia,
    só registra a mudança no histórico da compra."""
    pag = buscar_pagamento(conn, pagamento_id)
    mudancas = []
    if str(pag["valor"]) != str(novo_valor):
        mudancas.append(("pagamento_valor", pag["valor"], novo_valor))
    if pag["data"] != nova_data:
        mudancas.append(("pagamento_data", pag["data"], nova_data))
    if (pag["forma_pagamento"] or "") != (nova_forma_pagamento or ""):
        mudancas.append(("pagamento_forma", pag["forma_pagamento"], nova_forma_pagamento))

    conn.execute(
        "UPDATE pagamentos SET valor = ?, data = ?, forma_pagamento = ? WHERE id = ?",
        (novo_valor, nova_data, nova_forma_pagamento, pagamento_id),
    )
    for campo, antigo, novo in mudancas:
        conn.execute(
            "INSERT INTO historico_edicoes (compra_id, campo, valor_antigo, valor_novo, data) VALUES (?, ?, ?, ?, ?)",
            (pag["compra_id"], campo, str(antigo), str(novo), hoje()),
        )
    conn.commit()


def excluir_pagamento(conn, pagamento_id):
    """Estorna um pagamento lançado errado. Fica registrado no histórico da compra."""
    pag = buscar_pagamento(conn, pagamento_id)
    conn.execute(
        "INSERT INTO historico_edicoes (compra_id, campo, valor_antigo, valor_novo, data) VALUES (?, ?, ?, ?, ?)",
        (pag["compra_id"], "pagamento_estornado", f"R$ {pag['valor']:.2f} em {pag['data']}", "estornado", hoje()),
    )
    conn.execute("DELETE FROM pagamentos WHERE id = ?", (pagamento_id,))
    conn.commit()


# ---------- Produtos (sincronizado do CATALOGO.csv do Cláudio) ----------

def listar_produtos(conn, busca=None):
    """Sem `busca`, lista tudo. Com `busca`, filtra em Python (não dá pra fazer
    o SQL LIKE ignorar acento) comparando nome/código/marca já normalizados —
    mesmo critério do resto do app: sem acento, por trecho, não precisa ser
    a palavra inteira nem bater a caixa."""
    linhas = conn.execute("SELECT * FROM produtos ORDER BY marca, nome").fetchall()
    if not busca:
        return linhas
    termo = _normalizar_texto(busca)
    resultado = []
    for p in linhas:
        campos = (p["nome"], p["codigo"], p["marca"])
        if any(termo in _normalizar_texto(campo) for campo in campos if campo):
            resultado.append(p)
    return resultado


def buscar_produto(conn, codigo):
    return conn.execute("SELECT * FROM produtos WHERE codigo = ?", (codigo,)).fetchone()


def upsert_produto(conn, produto: dict):
    conn.execute(
        """
        INSERT INTO produtos (codigo, id_origem, nome, marca, tipo, genero, categoria,
                               numeracao, preco_venda, preco_custo, linha, status_catalogo, atualizado_em)
        VALUES (:codigo, :id_origem, :nome, :marca, :tipo, :genero, :categoria,
                :numeracao, :preco_venda, :preco_custo, :linha, :status_catalogo, :atualizado_em)
        ON CONFLICT(codigo) DO UPDATE SET
            id_origem = excluded.id_origem,
            nome = excluded.nome,
            marca = excluded.marca,
            tipo = excluded.tipo,
            genero = excluded.genero,
            categoria = excluded.categoria,
            numeracao = excluded.numeracao,
            preco_venda = excluded.preco_venda,
            linha = excluded.linha,
            status_catalogo = excluded.status_catalogo,
            atualizado_em = excluded.atualizado_em
        """,
        produto,
    )
    # preco_custo nunca é sobrescrito pelo import — é preenchido à mão dentro do app
    # (o CATALOGO.csv do Cláudio só tem preço de venda, não tem custo).


def definir_custo_produto(conn, codigo, preco_custo):
    conn.execute("UPDATE produtos SET preco_custo = ? WHERE codigo = ?", (preco_custo, codigo))
    conn.commit()


PREFIXO_PRODUTO_MANUAL = "MANUAL"


def gerar_codigo_produto_manual(conn):
    """Gera um código MANUALxxx sequencial, pro cadastro rápido de produto direto
    na tela de venda/compra. Prefixo distinto do padrão do Cláudio (ex.: AD001) pra
    nunca colidir com um código real que venha depois pelo CATALOGO.csv."""
    maior = 0
    linhas = conn.execute(
        "SELECT codigo FROM produtos WHERE codigo LIKE ?", (f"{PREFIXO_PRODUTO_MANUAL}%",)
    ).fetchall()
    for linha in linhas:
        resto = linha["codigo"][len(PREFIXO_PRODUTO_MANUAL):]
        if resto.isdigit():
            maior = max(maior, int(resto))
    return f"{PREFIXO_PRODUTO_MANUAL}{maior + 1:03d}"


def criar_produto_rapido(conn, nome, marca, preco_venda, codigo=None):
    """Cadastro rápido de produto, feito direto da tela de Nova venda/Nova compra
    quando o item não está no catálogo importado. Entra na mesma tabela `produtos`
    usada pelo import do CATALOGO.csv — o upsert por código nunca sobrescreve um
    produto existente aqui porque quem chama já checou que o código está livre."""
    if not codigo:
        codigo = gerar_codigo_produto_manual(conn)
    produto = {
        "codigo": codigo,
        "id_origem": None,
        "nome": nome.strip(),
        "marca": (marca or "").strip() or None,
        "tipo": None,
        "genero": None,
        "categoria": None,
        "numeracao": None,
        "preco_venda": preco_venda,
        "preco_custo": None,
        "linha": None,
        "status_catalogo": "CADASTRO MANUAL (APP)",
        "atualizado_em": hoje(),
    }
    upsert_produto(conn, produto)
    conn.commit()
    return buscar_produto(conn, codigo)


# ---------- Vendas (todas as compras, de todos os clientes, numa lista só) ----------

def listar_vendas(conn):
    linhas = conn.execute(
        """
        SELECT compras.*, clientes.nome AS cliente_nome
        FROM compras
        JOIN clientes ON clientes.id = compras.cliente_id
        ORDER BY compras.data DESC, compras.id DESC
        """
    ).fetchall()
    resultado = []
    for c in linhas:
        saldo, pago = saldo_compra(conn, c)
        resultado.append({**dict(c), "saldo": saldo, "pago": pago})
    return resultado


# ---------- Relatórios ----------

def _atraso_compra(conn, compra):
    """Mesma lógica usada no resumo do painel, isolada aqui pra reaproveitar por cliente."""
    saldo, pago = saldo_compra(conn, compra)
    if saldo <= 0:
        return 0.0, saldo
    parcelas = parcelas_compra(conn, compra["id"])
    if not parcelas:
        return 0.0, saldo
    hoje_str = hoje()
    vencido_previsto = sum(p["valor_previsto"] for p in parcelas if p["vencimento"] <= hoje_str)
    atraso = max(0.0, min(saldo, vencido_previsto - pago))
    return round(atraso, 2), saldo


def vendas_mensais(conn):
    """Total vendido (valor das compras registradas) por mês — não é caixa, é venda."""
    linhas = conn.execute(
        """
        SELECT substr(data, 1, 7) AS mes, COUNT(*) AS qtd, SUM(valor_total) AS total
        FROM compras
        GROUP BY mes
        ORDER BY mes DESC
        """
    ).fetchall()
    return [{"mes": l["mes"], "qtd_compras": l["qtd"], "total_vendido": round(l["total"], 2)} for l in linhas]


def clientes_atrasados(conn):
    """Clientes com pelo menos uma parcela vencida ainda não coberta pelo total pago."""
    resultado = {}
    for c in conn.execute("SELECT * FROM compras").fetchall():
        atraso, saldo = _atraso_compra(conn, c)
        if atraso <= 0:
            continue
        cliente_id = c["cliente_id"]
        resultado.setdefault(cliente_id, {"atraso": 0.0, "num_compras": 0})
        resultado[cliente_id]["atraso"] += atraso
        resultado[cliente_id]["num_compras"] += 1
    lista = []
    for cliente_id, dados in resultado.items():
        cliente = buscar_cliente(conn, cliente_id)
        lista.append({**dict(cliente), "atraso": round(dados["atraso"], 2), "num_compras": dados["num_compras"]})
    lista.sort(key=lambda x: -x["atraso"])
    return lista


def clientes_em_aberto(conn):
    """Clientes com saldo pendente, atrasado ou não — visão ampla de fiado em aberto."""
    resultado = {}
    for c in conn.execute("SELECT * FROM compras").fetchall():
        saldo, _ = saldo_compra(conn, c)
        if saldo <= 0:
            continue
        cliente_id = c["cliente_id"]
        resultado.setdefault(cliente_id, {"saldo": 0.0, "num_compras": 0})
        resultado[cliente_id]["saldo"] += saldo
        resultado[cliente_id]["num_compras"] += 1
    lista = []
    for cliente_id, dados in resultado.items():
        cliente = buscar_cliente(conn, cliente_id)
        lista.append({**dict(cliente), "saldo_total": round(dados["saldo"], 2), "num_compras": dados["num_compras"]})
    lista.sort(key=lambda x: -x["saldo_total"])
    return lista


def clientes_sem_compra(conn, dias):
    """Clientes que não compram há X dias — inclui quem nunca comprou nada."""
    from datetime import timedelta

    corte = (date.today() - timedelta(days=dias)).isoformat()
    lista = []
    for cliente in listar_clientes(conn):
        ultima = conn.execute(
            "SELECT MAX(data) AS ultima FROM compras WHERE cliente_id = ?", (cliente["id"],)
        ).fetchone()["ultima"]
        if ultima is None or ultima < corte:
            lista.append({**dict(cliente), "ultima_compra": ultima})
    lista.sort(key=lambda x: x["ultima_compra"] or "")
    return lista


def produtos_mais_vendidos(conn):
    """Ranking por descrição de produto (texto da própria compra) — quantas vezes
    foi vendido e quanto rendeu no total. Compras com vários itens juntos na mesma
    descrição (ex.: "Tênis A; Tênis B") contam como uma linha só, já que a compra
    não guarda item por item, só a descrição livre digitada na hora da venda."""
    linhas = conn.execute("SELECT descricao, valor_total FROM compras").fetchall()
    agregados = {}
    for l in linhas:
        chave = _normalizar_texto(l["descricao"])
        if chave not in agregados:
            agregados[chave] = {"descricao": l["descricao"], "qtd": 0, "total_vendido": 0.0}
        agregados[chave]["qtd"] += 1
        agregados[chave]["total_vendido"] += l["valor_total"]
    resultado = list(agregados.values())
    for r in resultado:
        r["total_vendido"] = round(r["total_vendido"], 2)
    resultado.sort(key=lambda r: (-r["qtd"], -r["total_vendido"]))
    return resultado


# ---------- Dashboard ----------

def resumo_geral(conn):
    """Total a receber, em atraso (parcela vencida ainda não coberta pelo total pago) e a vencer."""
    compras = conn.execute("SELECT * FROM compras").fetchall()
    total_receber = 0.0
    total_atraso = 0.0
    total_a_vencer = 0.0
    hoje_str = hoje()
    for c in compras:
        saldo, pago = saldo_compra(conn, c)
        if saldo <= 0:
            continue
        total_receber += saldo
        parcelas = parcelas_compra(conn, c["id"])
        if not parcelas:
            total_a_vencer += saldo
            continue
        vencido_previsto = sum(p["valor_previsto"] for p in parcelas if p["vencimento"] <= hoje_str)
        atraso = max(0.0, min(saldo, vencido_previsto - pago))
        total_atraso += atraso
        total_a_vencer += max(0.0, saldo - atraso)
    return {
        "total_receber": round(total_receber, 2),
        "total_atraso": round(total_atraso, 2),
        "total_a_vencer": round(total_a_vencer, 2),
    }
