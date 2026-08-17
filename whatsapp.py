"""Monta link 'clique pra conversar' do WhatsApp (wa.me).

Não existe API oficial de grupo/contato avulso que anexe arquivo automaticamente —
o wa.me só pré-preenche texto e abre a conversa já com o número certo. Anexar a imagem
do comprovante continua sendo manual (print da tela do comprovante + anexar no WhatsApp),
mesmo padrão de captura que já é usado no projeto.
"""
import re
from urllib.parse import quote


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
    texto = (
        f"Oi, {nome_cliente}! 💗 Aqui está o comprovante do seu pagamento de "
        f"R$ {valor:.2f} (dia {data_str}). Já anexo o print certinho por aqui!"
    )
    return f"https://wa.me/{numero}?text={quote(texto)}"
