"""Monta link 'clique pra conversar' do WhatsApp (wa.me).

Não existe API oficial de grupo/contato avulso que anexe arquivo automaticamente —
o wa.me só pré-preenche texto e abre a conversa já com o número certo. Anexar a imagem
do comprovante continua sendo manual (print da tela do comprovante + anexar no WhatsApp),
mesmo padrão de captura que já é usado no projeto.
"""
import re
from urllib.parse import quote


def _moeda_br(valor: float) -> str:
    """Mesmo formato brasileiro usado na tela (1234.5 -> '1.234,50'), pra mensagem
    de WhatsApp ficar igual ao que o cliente já vê no comprovante/carnê."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def normalizar_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return digitos


def link_comprovante(telefone: str, nome_cliente: str, valor: float, data_str: str) -> str | None:
    numero = normalizar_telefone(telefone)
    if not numero:
        return None
    texto = f"{nome_cliente}, segue o comprovante do seu pagamento de R$ {_moeda_br(valor)}! 💗"
    return f"https://wa.me/{numero}?text={quote(texto)}"


def link_carne(telefone: str, nome_cliente: str, descricao: str, valor_total: float) -> str | None:
    numero = normalizar_telefone(telefone)
    if not numero:
        return None
    texto = (
        f"{nome_cliente}, segue o carnê da sua compra ({descricao}) — "
        f"total de R$ {_moeda_br(valor_total)}. 💗"
    )
    return f"https://wa.me/{numero}?text={quote(texto)}"
