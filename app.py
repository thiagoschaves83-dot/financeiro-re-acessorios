"""App financeiro da Rê Acessórios — Flask, uso pessoal do Thiago."""
import csv
import io
import os

from flask import Flask, render_template, request, redirect, url_for, flash, Response, session, send_file

import auth
import db
import importar_catalogo
import whatsapp

app = Flask(__name__)
app.secret_key = auth.obter_secret_key()

# Cookie de sessão mais seguro — importa a partir do momento que o app deixa de
# estar isolado numa rede privada e passa a responder na internet aberta.
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG") != "1"  # exige HTTPS, salvo em teste local
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

db.init_db()


@app.template_filter("moeda_br")
def moeda_br(valor):
    """Formata número pro padrão brasileiro de moeda: 1234.5 vira '1.234,50'
    (ponto separando milhar, vírgula separando centavo) — só pra exibição na tela,
    não usar em campo de formulário (o valor volta pro servidor com vírgula decimal,
    então um ponto de milhar juntado quebraria o `.replace(",", ".")` do parser)."""
    if valor is None:
        return valor
    texto = f"{valor:,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


@app.template_filter("data_br")
def data_br(valor):
    """Converte AAAA-MM-DD (formato interno) pra DD/MM/AAAA (formato de exibição)."""
    if not valor:
        return valor
    partes = valor.split("-")
    if len(partes) != 3:
        return valor
    ano, mes, dia = partes
    return f"{dia}/{mes}/{ano}"


@app.before_request
def exigir_login():
    rotas_livres = {"login", "definir_senha", "static"}
    if request.endpoint in rotas_livres:
        return
    if not auth.senha_definida():
        return redirect(url_for("definir_senha"))
    if not session.get("autenticado"):
        return redirect(url_for("login"))


@app.route("/definir-senha", methods=["GET", "POST"])
def definir_senha():
    if auth.senha_definida():
        # só dá pra definir a senha uma vez por essa tela — depois de criada, é sempre login.
        # evita que alguém de fora tente "redefinir" a senha remotamente.
        return redirect(url_for("login"))
    if request.method == "POST":
        senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar", "")
        if len(senha) < 4:
            flash("Escolha uma senha com pelo menos 4 caracteres.", "erro")
        elif senha != confirmar:
            flash("As duas senhas digitadas não bateram.", "erro")
        else:
            auth.definir_senha(senha)
            session["autenticado"] = True
            flash("Senha definida. Guarde ela — é a mesma pra acessar do celular.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("definir_senha.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    pode, segundos = auth.pode_tentar_login()
    if request.method == "POST":
        if not pode:
            flash(f"Muitas tentativas erradas. Espera {segundos // 60 + 1} minuto(s) e tenta de novo.", "erro")
        else:
            senha = request.form.get("senha", "")
            if auth.verificar_senha(senha):
                auth.registrar_sucesso_login()
                session["autenticado"] = True
                return redirect(url_for("dashboard"))
            auth.registrar_falha_login()
            flash("Senha incorreta.", "erro")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/backup")
def backup():
    """Baixa o dados.db atual. No PC, o iniciar.ps1 já faz backup automático a cada
    abertura — na nuvem não tem tarefa agendada no plano grátis, então esse botão
    substitui isso: o Thiago clica de vez em quando pra guardar uma cópia."""
    from datetime import datetime

    nome = f"backup_financeiro_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    return send_file(db.DB_PATH, as_attachment=True, download_name=nome)


@app.route("/")
def dashboard():
    conn = db.get_conn()
    resumo = db.resumo_geral(conn)
    clientes = db.listar_clientes(conn)
    conn.close()
    return render_template("dashboard.html", resumo=resumo, total_clientes=len(clientes))


# ---------- Clientes ----------

@app.route("/clientes")
def clientes():
    conn = db.get_conn()
    busca = request.args.get("q", "").strip() or None
    lista = []
    for c in db.listar_clientes(conn, busca):
        compras = db.listar_compras_cliente(conn, c["id"])
        saldo_total = round(sum(x["saldo"] for x in compras if x["saldo"] > 0), 2)
        lista.append({**dict(c), "saldo_total": saldo_total, "num_compras": len(compras)})
    conn.close()
    return render_template("clientes.html", clientes=lista, busca=busca or "")


@app.route("/clientes/novo", methods=["POST"])
def novo_cliente():
    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    if not nome:
        flash("Nome é obrigatório.", "erro")
        return redirect(url_for("clientes"))
    conn = db.get_conn()
    cliente_id = db.criar_cliente(conn, nome, telefone)
    conn.close()
    return redirect(url_for("cliente_detalhe", cliente_id=cliente_id))


@app.route("/clientes/verificar-duplicado")
def verificar_cliente_duplicado():
    """Usado via fetch pela tela de cadastro de cliente, pra avisar (sem bloquear)
    se já existe alguém com o mesmo nome ou telefone antes do Thiago confirmar."""
    nome = request.args.get("nome", "").strip()
    telefone = request.args.get("telefone", "").strip()
    if not nome and not telefone:
        return {"duplicados": []}
    conn = db.get_conn()
    duplicados = db.buscar_clientes_duplicados(conn, nome, telefone)
    conn.close()
    return {"duplicados": duplicados}


@app.route("/clientes/<int:cliente_id>")
def cliente_detalhe(cliente_id):
    conn = db.get_conn()
    cliente = db.buscar_cliente(conn, cliente_id)
    compras = db.listar_compras_cliente(conn, cliente_id)
    produtos = db.listar_produtos(conn)
    conn.close()
    abrir_edicao = request.args.get("editar") == "1"
    return render_template("cliente_detalhe.html", cliente=cliente, compras=compras, produtos=produtos, abrir_edicao=abrir_edicao)


@app.route("/clientes/<int:cliente_id>/editar", methods=["POST"])
def editar_cliente(cliente_id):
    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    if not nome:
        flash("Nome é obrigatório.", "erro")
        return redirect(url_for("cliente_detalhe", cliente_id=cliente_id))
    conn = db.get_conn()
    db.editar_cliente(conn, cliente_id, nome, telefone)
    conn.close()
    flash("Dados do cliente atualizados.", "ok")
    return redirect(url_for("cliente_detalhe", cliente_id=cliente_id))


# ---------- Compras ----------

def _itens_do_form():
    """Lê os produtos de uma venda/compra com vários itens (nome + valor de cada um,
    na mesma ordem) — usado pro carnê mostrar em lista em vez de um texto só."""
    descricoes = request.form.getlist("item_descricao")
    valores = request.form.getlist("item_valor")
    itens = []
    for i, desc in enumerate(descricoes):
        if not desc.strip():
            continue
        valor_raw = valores[i] if i < len(valores) else ""
        valor = float(valor_raw.replace(",", ".")) if valor_raw.strip() else 0
        itens.append({"descricao": desc.strip(), "valor": valor})
    return itens


@app.route("/clientes/<int:cliente_id>/compras/nova", methods=["POST"])
def nova_compra(cliente_id):
    descricao = request.form.get("descricao", "").strip()
    valor_total = float(request.form.get("valor_total", "0").replace(",", "."))
    entrada_raw = request.form.get("entrada", "").strip()
    entrada = float(entrada_raw.replace(",", ".")) if entrada_raw else 0
    datas_parcelas = request.form.getlist("data_parcela")
    valores_parcelas = [
        float(v.replace(",", ".")) if v.strip() else None
        for v in request.form.getlist("valor_parcela")
    ]
    itens = _itens_do_form()
    conn = db.get_conn()
    compra_id = db.criar_compra(conn, cliente_id, descricao, valor_total, datas_parcelas, entrada=entrada, valores_parcelas=valores_parcelas, itens=itens)
    conn.close()
    return redirect(url_for("carne", compra_id=compra_id))


@app.route("/compras/<int:compra_id>")
def compra_detalhe(compra_id):
    conn = db.get_conn()
    compra = db.buscar_compra(conn, compra_id)
    if not compra:
        conn.close()
        flash("Essa compra não existe mais — pode ter sido excluída.", "erro")
        return redirect(url_for("vendas"))
    cliente = db.buscar_cliente(conn, compra["cliente_id"])
    saldo, pago = db.saldo_compra(conn, compra)
    parcelas = db.parcelas_com_status(conn, compra_id)
    pagamentos = db.pagamentos_compra(conn, compra_id)
    historico = db.historico_compra(conn, compra_id)
    itens = db.itens_compra_para_exibir(conn, compra)
    conn.close()
    return render_template(
        "compra_detalhe.html",
        compra=compra,
        cliente=cliente,
        saldo=saldo,
        pago=pago,
        parcelas=parcelas,
        pagamentos=pagamentos,
        historico=historico,
        itens=itens,
    )


@app.route("/compras/<int:compra_id>/editar", methods=["GET", "POST"])
def editar_compra(compra_id):
    conn = db.get_conn()
    compra = db.buscar_compra(conn, compra_id)
    if not compra:
        conn.close()
        flash("Essa compra não existe mais — pode ter sido excluída.", "erro")
        return redirect(url_for("vendas"))
    if request.method == "POST":
        novo_valor = float(request.form.get("valor_total", "0").replace(",", "."))
        nova_descricao = request.form.get("descricao", "").strip()
        if not nova_descricao:
            conn.close()
            flash("Descrição do produto é obrigatória.", "erro")
            return redirect(url_for("editar_compra", compra_id=compra_id))
        db.editar_compra(conn, compra_id, novo_valor, nova_descricao)
        datas_parcelas = request.form.getlist("data_parcela")
        valores_parcelas = [
            float(v.replace(",", ".")) if v.strip() else None
            for v in request.form.getlist("valor_parcela")
        ]
        db.redefinir_parcelas(conn, compra_id, datas_parcelas, valores_parcelas)
        conn.close()
        flash("Compra atualizada — o saldo e as parcelas já recalcularam sozinhos.", "ok")
        return redirect(url_for("compra_detalhe", compra_id=compra_id))
    produtos = db.listar_produtos(conn)
    parcelas = db.parcelas_compra(conn, compra_id)
    entrada = sum(
        p["valor"] for p in db.pagamentos_compra(conn, compra_id)
        if (p["forma_pagamento"] or "") == "Entrada"
    )
    conn.close()
    return render_template("editar_compra.html", compra=compra, produtos=produtos, parcelas=parcelas, entrada=entrada)


@app.route("/compras/<int:compra_id>/excluir", methods=["POST"])
def excluir_compra(compra_id):
    """Só permite excluir a compra se ela ainda não tiver nenhum pagamento registrado
    — se já tiver, o Thiago precisa estornar o(s) pagamento(s) primeiro (fluxo que já
    existe em cada pagamento). Exclui junto parcelas e histórico, sem deixar órfão."""
    conn = db.get_conn()
    compra = db.buscar_compra(conn, compra_id)
    if not compra:
        conn.close()
        flash("Compra não encontrada.", "erro")
        return redirect(url_for("vendas"))
    cliente_id = compra["cliente_id"]
    _, pago = db.saldo_compra(conn, compra)
    if pago > 0:
        conn.close()
        flash("Essa compra já tem pagamento registrado — estorne o(s) pagamento(s) primeiro pra poder excluir.", "erro")
        return redirect(url_for("compra_detalhe", compra_id=compra_id))
    db.excluir_compra(conn, compra_id)
    conn.close()
    flash("Compra excluída.", "ok")
    return redirect(url_for("cliente_detalhe", cliente_id=cliente_id))


# ---------- Pagamentos (baixa) ----------

@app.route("/compras/<int:compra_id>/pagamento", methods=["POST"])
def novo_pagamento(compra_id):
    valor = float(request.form.get("valor", "0").replace(",", "."))
    forma = request.form.get("forma_pagamento", "").strip()
    data_pagamento = request.form.get("data") or db.hoje()
    conn = db.get_conn()
    # registra com a data de hoje e, se o Thiago já souber a data real (ex.: Pix caiu antes),
    # corrige na hora — evita o passo extra de precisar editar depois
    pagamento_id = db.registrar_pagamento(conn, compra_id, valor, forma)
    if data_pagamento != db.hoje():
        db.editar_pagamento(conn, pagamento_id, valor, data_pagamento, forma)
    conn.close()
    return redirect(url_for("comprovante", compra_id=compra_id, pagamento_id=pagamento_id))


@app.route("/pagamentos/<int:pagamento_id>/editar", methods=["GET", "POST"])
def editar_pagamento(pagamento_id):
    conn = db.get_conn()
    pagamento = db.buscar_pagamento(conn, pagamento_id)
    if request.method == "POST":
        novo_valor = float(request.form.get("valor", "0").replace(",", "."))
        nova_data = request.form.get("data")
        nova_forma = request.form.get("forma_pagamento", "").strip()
        db.editar_pagamento(conn, pagamento_id, novo_valor, nova_data, nova_forma)
        compra_id = pagamento["compra_id"]
        conn.close()
        flash("Pagamento atualizado — inclusive a data, se você mudou.", "ok")
        return redirect(url_for("compra_detalhe", compra_id=compra_id))
    conn.close()
    return render_template("editar_pagamento.html", pagamento=pagamento)


@app.route("/pagamentos/<int:pagamento_id>/excluir", methods=["POST"])
def excluir_pagamento(pagamento_id):
    conn = db.get_conn()
    pagamento = db.buscar_pagamento(conn, pagamento_id)
    compra_id = pagamento["compra_id"]
    db.excluir_pagamento(conn, pagamento_id)
    conn.close()
    flash("Pagamento estornado — fica registrado no histórico da compra.", "ok")
    return redirect(url_for("compra_detalhe", compra_id=compra_id))


@app.route("/compras/<int:compra_id>/comprovante/<int:pagamento_id>")
def comprovante(compra_id, pagamento_id):
    conn = db.get_conn()
    compra = db.buscar_compra(conn, compra_id)
    cliente = db.buscar_cliente(conn, compra["cliente_id"])
    pagamento = db.buscar_pagamento(conn, pagamento_id)
    saldo, pago = db.saldo_compra(conn, compra)
    conn.close()
    link_zap = whatsapp.link_comprovante(cliente["telefone"], cliente["nome"], pagamento["valor"], pagamento["data"])
    return render_template(
        "comprovante.html",
        compra=compra,
        cliente=cliente,
        pagamento=pagamento,
        saldo=saldo,
        link_zap=link_zap,
    )


@app.route("/compras/<int:compra_id>/carne")
def carne(compra_id):
    conn = db.get_conn()
    compra = db.buscar_compra(conn, compra_id)
    if not compra:
        conn.close()
        flash("Compra não encontrada.", "erro")
        return redirect(url_for("vendas"))
    cliente = db.buscar_cliente(conn, compra["cliente_id"])
    parcelas = db.parcelas_com_status(conn, compra_id)
    saldo, pago = db.saldo_compra(conn, compra)
    itens = db.itens_compra_para_exibir(conn, compra)
    conn.close()
    link_zap = whatsapp.link_carne(cliente["telefone"], cliente["nome"], compra["descricao"], compra["valor_total"])
    return render_template(
        "carne.html",
        compra=compra,
        cliente=cliente,
        parcelas=parcelas,
        saldo=saldo,
        pago=pago,
        itens=itens,
        link_zap=link_zap,
    )


# ---------- Vendas (lista de todas as compras, de todos os clientes) ----------

@app.route("/vendas")
def vendas():
    conn = db.get_conn()
    busca = request.args.get("q", "").strip() or None
    lista = db.listar_vendas(conn)
    if busca:
        termo = db._normalizar_texto(busca)
        lista = [
            v for v in lista
            if termo in db._normalizar_texto(v["cliente_nome"]) or termo in db._normalizar_texto(v["descricao"])
        ]
    clientes_nomes = [c["nome"] for c in db.listar_clientes(conn)]
    produtos = db.listar_produtos(conn)
    conn.close()
    return render_template("vendas.html", vendas=lista, clientes_nomes=clientes_nomes, produtos=produtos, busca=busca or "")


@app.route("/vendas/nova", methods=["POST"])
def nova_venda():
    nome_cliente = request.form.get("cliente", "").strip()
    telefone = request.form.get("telefone", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_total_raw = request.form.get("valor_total", "0").replace(",", ".")
    entrada_raw = request.form.get("entrada", "").strip()
    datas_parcelas = request.form.getlist("data_parcela")

    if not nome_cliente:
        flash("Nome do cliente é obrigatório.", "erro")
        return redirect(url_for("vendas"))
    if not descricao:
        flash("Descrição do produto é obrigatória.", "erro")
        return redirect(url_for("vendas"))
    try:
        valor_total = float(valor_total_raw)
        entrada = float(entrada_raw.replace(",", ".")) if entrada_raw else 0
        valores_parcelas = [
            float(v.replace(",", ".")) if v.strip() else None
            for v in request.form.getlist("valor_parcela")
        ]
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("vendas"))

    conn = db.get_conn()
    cliente = db.buscar_cliente_por_nome(conn, nome_cliente)
    if cliente:
        cliente_id = cliente["id"]
        aviso = f"Venda lançada para o cliente já cadastrado: {cliente['nome']}."
    else:
        cliente_id = db.criar_cliente(conn, nome_cliente, telefone)
        aviso = f"Cliente novo criado: {nome_cliente}. Se já existia com outro nome, corrija pra não duplicar."

    itens = _itens_do_form()
    compra_id = db.criar_compra(conn, cliente_id, descricao, valor_total, datas_parcelas, entrada=entrada, valores_parcelas=valores_parcelas, itens=itens)
    conn.close()
    flash(aviso, "ok")
    return redirect(url_for("carne", compra_id=compra_id))


# ---------- Produtos (sincronizados do catálogo do Cláudio) ----------

@app.route("/produtos")
def produtos():
    conn = db.get_conn()
    busca = request.args.get("q", "").strip() or None
    lista = db.listar_produtos(conn, busca)
    conn.close()
    return render_template("produtos.html", produtos=lista, busca=busca or "")


@app.route("/produtos/importar", methods=["POST"])
def importar_produtos():
    resultado = importar_catalogo.importar()
    if resultado["ok"]:
        flash(f"{resultado['total']} produtos importados/atualizados do CATALOGO.csv.", "ok")
    else:
        flash(f"Não consegui importar: {resultado['erro']}", "erro")
    return redirect(url_for("produtos"))


@app.route("/produtos/importar-upload", methods=["POST"])
def importar_produtos_upload():
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Nenhum arquivo selecionado.", "erro")
        return redirect(url_for("produtos"))
    try:
        texto = arquivo.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Não consegui ler esse arquivo — confirma que é o CATALOGO.csv exportado certinho.", "erro")
        return redirect(url_for("produtos"))
    resultado = importar_catalogo.processar_conteudo(texto)
    flash(f"{resultado['total']} produtos importados/atualizados do arquivo enviado.", "ok")
    return redirect(url_for("produtos"))


@app.route("/produtos/rapido", methods=["POST"])
def cadastrar_produto_rapido():
    """Cadastro rápido de produto direto da tela de Nova venda/Nova compra, via fetch —
    devolve JSON pro JS colocar o produto no datalist na hora, sem sair do fluxo de
    lançar a venda/compra. Não mexe no CATALOGO.csv — só entra na tabela `produtos`."""
    nome = request.form.get("nome", "").strip()
    marca = request.form.get("marca", "").strip()
    codigo = request.form.get("codigo", "").strip().upper()
    preco_raw = request.form.get("preco_venda", "").strip()

    if not nome:
        return {"ok": False, "erro": "Nome do produto é obrigatório."}, 400

    preco_venda = None
    if preco_raw:
        try:
            preco_venda = float(preco_raw.replace(",", "."))
        except ValueError:
            return {"ok": False, "erro": "Preço inválido."}, 400

    conn = db.get_conn()
    if codigo and db.buscar_produto(conn, codigo):
        conn.close()
        return {"ok": False, "erro": f"Já existe um produto com o código {codigo}."}, 400

    produto = db.criar_produto_rapido(conn, nome, marca, preco_venda, codigo or None)
    conn.close()
    return {"ok": True, "produto": dict(produto)}


@app.route("/produtos/<codigo>/custo", methods=["POST"])
def definir_custo(codigo):
    preco_custo_raw = request.form.get("preco_custo", "").strip()
    conn = db.get_conn()
    if preco_custo_raw:
        db.definir_custo_produto(conn, codigo, float(preco_custo_raw.replace(",", ".")))
    conn.close()
    return redirect(url_for("produtos"))


# ---------- Relatórios ----------

def _csv_response(nome_arquivo, cabecalho, linhas):
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow(linha)
    return Response(
        saida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@app.route("/relatorio/clientes.csv")
def relatorio_clientes_csv():
    conn = db.get_conn()
    linhas = []
    for cliente in db.listar_clientes(conn):
        for c in db.listar_compras_cliente(conn, cliente["id"]):
            linhas.append([cliente["nome"], cliente["telefone"], c["descricao"], c["data"], c["valor_total"], c["pago"], c["saldo"]])
    conn.close()
    return _csv_response("relatorio_clientes.csv", ["Cliente", "Telefone", "Compra", "Data", "Valor Total", "Pago", "Saldo"], linhas)


@app.route("/relatorio/produtos.csv")
def relatorio_produtos_csv():
    conn = db.get_conn()
    linhas = [
        [p["codigo"], p["nome"], p["marca"], p["numeracao"], p["preco_venda"], p["preco_custo"],
         (round(p["preco_venda"] - p["preco_custo"], 2) if p["preco_venda"] and p["preco_custo"] else "")]
        for p in db.listar_produtos(conn)
    ]
    conn.close()
    return _csv_response("relatorio_produtos.csv", ["Código", "Nome", "Marca", "Numeração", "Preço venda", "Custo", "Margem"], linhas)


@app.route("/relatorios")
def relatorios():
    return render_template("relatorios.html")


@app.route("/relatorios/vendas-mensais")
def relatorio_vendas_mensais():
    conn = db.get_conn()
    dados = db.vendas_mensais(conn)
    conn.close()
    return render_template("relatorio_vendas_mensais.html", dados=dados)


@app.route("/relatorios/vendas-mensais.csv")
def relatorio_vendas_mensais_csv():
    conn = db.get_conn()
    linhas = [[d["mes"], d["qtd_compras"], d["total_vendido"]] for d in db.vendas_mensais(conn)]
    conn.close()
    return _csv_response("vendas_mensais.csv", ["Mês", "Qtd. compras", "Total vendido"], linhas)


@app.route("/relatorios/clientes-atrasados")
def relatorio_clientes_atrasados():
    conn = db.get_conn()
    dados = db.clientes_atrasados(conn)
    conn.close()
    return render_template("relatorio_clientes_atrasados.html", dados=dados)


@app.route("/relatorios/produtos-mais-vendidos")
def relatorio_produtos_mais_vendidos():
    conn = db.get_conn()
    dados = db.produtos_mais_vendidos(conn)
    conn.close()
    return render_template("relatorio_produtos_mais_vendidos.html", dados=dados)


@app.route("/relatorios/produtos-mais-vendidos.csv")
def relatorio_produtos_mais_vendidos_csv():
    conn = db.get_conn()
    linhas = [[d["descricao"], d["qtd"], d["total_vendido"]] for d in db.produtos_mais_vendidos(conn)]
    conn.close()
    return _csv_response("produtos_mais_vendidos.csv", ["Descrição", "Qtd. vendida", "Total vendido"], linhas)


@app.route("/relatorios/clientes-atrasados.csv")
def relatorio_clientes_atrasados_csv():
    conn = db.get_conn()
    linhas = [[d["nome"], d["telefone"], d["num_compras"], d["atraso"]] for d in db.clientes_atrasados(conn)]
    conn.close()
    return _csv_response("clientes_atrasados.csv", ["Cliente", "Telefone", "Compras em atraso", "Total atrasado"], linhas)


@app.route("/relatorios/clientes-em-aberto")
def relatorio_clientes_em_aberto():
    conn = db.get_conn()
    dados = db.clientes_em_aberto(conn)
    conn.close()
    return render_template("relatorio_clientes_em_aberto.html", dados=dados)


@app.route("/relatorios/clientes-em-aberto.csv")
def relatorio_clientes_em_aberto_csv():
    conn = db.get_conn()
    linhas = [[d["nome"], d["telefone"], d["num_compras"], d["saldo_total"]] for d in db.clientes_em_aberto(conn)]
    conn.close()
    return _csv_response("clientes_em_aberto.csv", ["Cliente", "Telefone", "Compras em aberto", "Saldo total"], linhas)


@app.route("/relatorios/sem-compra")
def relatorio_sem_compra():
    dias = int(request.args.get("dias", 60))
    conn = db.get_conn()
    dados = db.clientes_sem_compra(conn, dias)
    conn.close()
    return render_template("relatorio_sem_compra.html", dados=dados, dias=dias)


@app.route("/relatorios/sem-compra.csv")
def relatorio_sem_compra_csv():
    dias = int(request.args.get("dias", 60))
    conn = db.get_conn()
    linhas = [[d["nome"], d["telefone"], d["ultima_compra"] or "nunca comprou"] for d in db.clientes_sem_compra(conn, dias)]
    conn.close()
    return _csv_response(f"clientes_sem_compra_{dias}dias.csv", ["Cliente", "Telefone", "Última compra"], linhas)


# ---------- Fornecedores ----------

@app.route("/fornecedores")
def fornecedores():
    conn = db.get_conn()
    lista = db.listar_fornecedores(conn)
    conn.close()
    return render_template("fornecedores.html", fornecedores=lista)


@app.route("/fornecedores/novo", methods=["POST"])
def novo_fornecedor():
    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    if not nome:
        flash("Nome do fornecedor é obrigatório.", "erro")
        return redirect(url_for("fornecedores"))
    conn = db.get_conn()
    db.criar_fornecedor(conn, nome, telefone)
    conn.close()
    flash("Fornecedor cadastrado.", "ok")
    return redirect(url_for("fornecedores"))


# ---------- Contas a pagar (compras, despesas, outras despesas, retiradas) ----------

@app.route("/contas-pagar")
def contas_pagar():
    conn = db.get_conn()
    db.gerar_ocorrencias_recorrentes(conn)
    lista = db.listar_contas_pagar(conn)
    fornecedores_lista = db.listar_fornecedores(conn)
    conn.close()
    return render_template("contas_pagar.html", contas=lista, fornecedores=fornecedores_lista)


@app.route("/contas-pagar/nova", methods=["POST"])
def nova_conta_pagar():
    categoria = request.form.get("categoria", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_total_raw = request.form.get("valor_total", "0").replace(",", ".")
    data_conta = request.form.get("data") or db.hoje()
    vencimento = request.form.get("vencimento", "").strip() or None
    fornecedor_id_raw = request.form.get("fornecedor_id", "").strip()
    fornecedor_id = int(fornecedor_id_raw) if fornecedor_id_raw else None

    if categoria not in ("compra", "despesa", "outra_despesa", "retirada"):
        flash("Categoria inválida.", "erro")
        return redirect(url_for("contas_pagar"))
    if not descricao:
        flash("Descrição é obrigatória.", "erro")
        return redirect(url_for("contas_pagar"))
    try:
        valor_total = float(valor_total_raw)
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("contas_pagar"))

    conn = db.get_conn()
    conta_id = db.criar_conta_pagar(conn, categoria, descricao, valor_total, data_conta, fornecedor_id=fornecedor_id, vencimento=vencimento)
    conn.close()
    flash("Conta lançada.", "ok")
    return redirect(url_for("conta_pagar_detalhe", conta_id=conta_id))


@app.route("/contas-pagar/<int:conta_id>")
def conta_pagar_detalhe(conta_id):
    conn = db.get_conn()
    conta = db.buscar_conta_pagar(conn, conta_id)
    if not conta:
        conn.close()
        flash("Conta não encontrada.", "erro")
        return redirect(url_for("contas_pagar"))
    fornecedor = db.buscar_fornecedor(conn, conta["fornecedor_id"]) if conta["fornecedor_id"] else None
    saldo, pago = db.saldo_conta_pagar(conn, conta)
    pagamentos = db.pagamentos_saida_conta(conn, conta_id)
    conn.close()
    return render_template(
        "conta_pagar_detalhe.html",
        conta=conta,
        fornecedor=fornecedor,
        saldo=saldo,
        pago=pago,
        pagamentos=pagamentos,
    )


@app.route("/contas-pagar/<int:conta_id>/pagamento", methods=["POST"])
def novo_pagamento_saida(conta_id):
    valor_raw = request.form.get("valor", "0").replace(",", ".")
    forma = request.form.get("forma_pagamento", "").strip()
    data_pagamento = request.form.get("data") or db.hoje()
    try:
        valor = float(valor_raw)
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("conta_pagar_detalhe", conta_id=conta_id))
    conn = db.get_conn()
    db.registrar_pagamento_saida(conn, conta_id, valor, forma, data_pagamento)
    conn.close()
    flash("Pagamento registrado — já entra no fluxo de caixa sozinho.", "ok")
    return redirect(url_for("conta_pagar_detalhe", conta_id=conta_id))


# ---------- Outras receitas ----------

@app.route("/outras-receitas")
def outras_receitas():
    conn = db.get_conn()
    lista = db.listar_outras_receitas(conn)
    conn.close()
    return render_template("outras_receitas.html", receitas=lista)


@app.route("/outras-receitas/nova", methods=["POST"])
def nova_outra_receita():
    descricao = request.form.get("descricao", "").strip()
    valor_raw = request.form.get("valor", "0").replace(",", ".")
    data_receita = request.form.get("data") or db.hoje()
    if not descricao:
        flash("Descrição é obrigatória.", "erro")
        return redirect(url_for("outras_receitas"))
    try:
        valor = float(valor_raw)
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("outras_receitas"))
    conn = db.get_conn()
    db.criar_outra_receita(conn, descricao, valor, data_receita)
    conn.close()
    flash("Receita lançada.", "ok")
    return redirect(url_for("outras_receitas"))


# ---------- Fluxo de caixa ----------

@app.route("/fluxo-caixa")
def fluxo_caixa():
    conn = db.get_conn()
    db.gerar_ocorrencias_recorrentes(conn)
    meses = db.fluxo_caixa_mensal(conn)
    conn.close()
    return render_template("fluxo_caixa.html", meses=meses)


@app.route("/recebimentos-mensais")
def recebimentos_mensais_view():
    conn = db.get_conn()
    meses = db.recebimentos_mensais(conn)
    conn.close()
    return render_template("recebimentos_mensais.html", meses=meses)


@app.route("/contas-a-pagar-mensais")
def contas_a_pagar_mensais_view():
    conn = db.get_conn()
    db.gerar_ocorrencias_recorrentes(conn)
    meses = db.contas_a_pagar_mensais(conn)
    conn.close()
    return render_template("contas_a_pagar_mensais.html", meses=meses)


# ---------- Despesas recorrentes (retirada do dono, mensalidade fixa, etc.) ----------

@app.route("/despesas-recorrentes")
def despesas_recorrentes():
    conn = db.get_conn()
    lista = db.listar_despesas_recorrentes(conn)
    conn.close()
    return render_template("despesas_recorrentes.html", recorrentes=lista)


@app.route("/despesas-recorrentes/nova", methods=["POST"])
def nova_despesa_recorrente():
    descricao = request.form.get("descricao", "").strip()
    categoria = request.form.get("categoria", "").strip()
    valor_raw = request.form.get("valor", "0").replace(",", ".")
    frequencia = request.form.get("frequencia", "").strip()
    data_inicio = request.form.get("data_inicio") or db.hoje()

    if categoria not in ("compra", "despesa", "outra_despesa", "retirada"):
        flash("Categoria inválida.", "erro")
        return redirect(url_for("despesas_recorrentes"))
    if frequencia not in ("semanal", "quinzenal", "mensal", "semestral"):
        flash("Frequência inválida.", "erro")
        return redirect(url_for("despesas_recorrentes"))
    if not descricao:
        flash("Descrição é obrigatória.", "erro")
        return redirect(url_for("despesas_recorrentes"))
    try:
        valor = float(valor_raw)
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("despesas_recorrentes"))

    conn = db.get_conn()
    db.criar_despesa_recorrente(conn, descricao, categoria, valor, frequencia, data_inicio)
    db.gerar_ocorrencias_recorrentes(conn)
    conn.close()
    flash("Despesa recorrente cadastrada — já projetada no fluxo de caixa e em Contas a Pagar.", "ok")
    return redirect(url_for("despesas_recorrentes"))


@app.route("/despesas-recorrentes/<int:rec_id>/editar", methods=["POST"])
def editar_despesa_recorrente(rec_id):
    novo_valor_raw = request.form.get("valor", "0").replace(",", ".")
    try:
        novo_valor = float(novo_valor_raw)
    except ValueError:
        flash("Valor inválido.", "erro")
        return redirect(url_for("despesas_recorrentes"))
    conn = db.get_conn()
    db.editar_despesa_recorrente(conn, rec_id, novo_valor)
    conn.close()
    flash("Valor atualizado — vale a partir das próximas ocorrências ainda não pagas.", "ok")
    return redirect(url_for("despesas_recorrentes"))


@app.route("/despesas-recorrentes/<int:rec_id>/encerrar", methods=["POST"])
def encerrar_despesa_recorrente(rec_id):
    conn = db.get_conn()
    db.encerrar_despesa_recorrente(conn, rec_id)
    conn.close()
    flash("Recorrência encerrada — não gera mais ocorrências novas.", "ok")
    return redirect(url_for("despesas_recorrentes"))


if __name__ == "__main__":
    # Esse bloco só roda se alguém executar "python app.py" diretamente (ex.: teste
    # local). Hospedagem tipo PythonAnywhere importa o objeto `app` via WSGI e nunca
    # passa por aqui — então debug=True aqui não é risco lá, mas mantemos desligado
    # por padrão de qualquer forma, e só liga com FLASK_DEBUG=1 explícito.
    #
    # use_reloader=False é proposital: o padrão do Flask fica vigiando os arquivos
    # do projeto pra reiniciar sozinho quando algo muda, mas isso é feito checando
    # a pasta a cada segundo — e a pasta está num drive de rede (Q:\). Depois de
    # alguns minutos parado, esse monitoramento sobre a rede falha e derruba o
    # servidor inteiro, dando a impressão de que "o app fecha sozinho". Sem o
    # reloader, o servidor fica de pé até você fechar a janela de verdade.
    #
    # host="0.0.0.0": aceita conexão de fora deste PC (necessário pro Tailscale
    # alcançar o servidor do celular, no uso local).
    modo_debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(debug=modo_debug, use_reloader=False, host="0.0.0.0", port=5000)
