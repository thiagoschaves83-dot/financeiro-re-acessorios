async function compartilharImagem(idElemento, nomeArquivo) {
  const botao = document.getElementById("btn-compartilhar");
  const textoOriginal = botao.textContent;
  botao.textContent = "Gerando imagem...";
  botao.disabled = true;
  try {
    const elemento = document.getElementById(idElemento);
    const canvas = await html2canvas(elemento, { scale: 2, backgroundColor: "#ffffff" });
    canvas.toBlob(async (blob) => {
      botao.textContent = textoOriginal;
      botao.disabled = false;
      if (!blob) return;
      const arquivo = new File([blob], nomeArquivo, { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [arquivo] })) {
        try {
          await navigator.share({ files: [arquivo] });
          return;
        } catch (erro) {
          if (erro && erro.name === "AbortError") return;
        }
      }
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = nomeArquivo;
      link.click();
    }, "image/png");
  } catch (erro) {
    botao.textContent = textoOriginal;
    botao.disabled = false;
    alert("Não consegui gerar a imagem. Tenta 'Imprimir / salvar PDF' como alternativa.");
  }
}
