# Como colocar o financeiro na nuvem (PythonAnywhere, grátis)

O código já está pronto do meu lado (senha mais segura, bloqueio de tentativas, backup manual, upload de catálogo). Faltam só os passos que só você pode fazer — criar as contas e ligar tudo.

## Passo 1 — Criar conta no GitHub (se você não tiver)

1. Acesse **github.com** → "Sign up"
2. Crie a conta (gratuita)
3. Depois de criada, clique em **"New repository"**
4. Nome sugerido: `financeiro-re-acessorios`
5. Marque como **Private** (privado — é dado de negócio, não precisa ser público)
6. **Não** marque "Add a README" (o projeto já tem os arquivos)
7. Clique em "Create repository"
8. Copia a URL que aparece (algo como `https://github.com/seu-usuario/financeiro-re-acessorios.git`) e me manda aqui

Assim que você me mandar essa URL, eu preparo o envio do código daqui — essa parte eu faço.

## Passo 2 — Criar conta no PythonAnywhere

1. Acesse **pythonanywhere.com** → "Pricing & signup" → **"Create a Beginner account"** (é a gratuita)
2. Confirme se pediu cartão de crédito ou não — quando escrevi este roteiro, a conta grátis não pedia, mas isso pode ter mudado. Se pedir cartão e você não quiser fornecer, me avisa que a gente repensa a hospedagem.
3. Escolha um nome de usuário — ele vira parte do endereço do site (`seunome.pythonanywhere.com`)

## Passo 3 — Trazer o código pro PythonAnywhere

Depois de logado no PythonAnywhere:

1. Vá em **"Consoles"** → **"Bash"** (abre um terminal dentro do navegador)
2. Cole o comando (eu troco a URL do GitHub pela que você me mandar):
   ```
   git clone https://github.com/SEU-USUARIO/financeiro-re-acessorios.git
   ```
3. Ainda no console Bash, instale as dependências:
   ```
   cd financeiro-re-acessorios
   pip install --user -r requirements.txt
   ```

## Passo 4 — Criar a Web App

1. Vá na aba **"Web"** → **"Add a new web app"**
2. Escolha **"Manual configuration"** (não "Flask" pronto — preferimos configurar na mão pra evitar confusão com a estrutura do projeto)
3. Escolha a versão do Python (a mais recente disponível)
4. Depois de criada, vai aparecer um link tipo **"WSGI configuration file"** — clique nele
5. Apague o conteúdo e cole isto (ajustando `SEU-USUARIO` pro seu usuário real):
   ```python
   import sys
   path = '/home/SEU-USUARIO/financeiro-re-acessorios'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```
6. Salve

## Passo 5 — Levar o banco de dados

1. Na aba **"Files"**, navegue até a pasta `financeiro-re-acessorios`
2. Clique em **"Upload a file"**
3. Envie o `dados.db` que está aqui no seu PC, em:
   `Q:\ADMINISTRAÇÃO\Frota\13 - Diversos\Thiago\Rê Acessórios\app-financeiro\dados.db`

## Passo 6 — Ligar

1. Volte na aba **"Web"** e clique no botão verde **"Reload"**
2. Abra a URL do seu site (`seunome.pythonanywhere.com`)
3. Como o hash de senha mudou de formato, vai pedir pra **definir a senha de novo** — escolha uma senha (pode ser diferente da do PC, já que agora são dois sistemas separados até você decidir aposentar o local)

## Depois de tudo funcionando

- Teste abrindo pelo celular com **Wi-Fi de casa desligado e o PC desligado** — esse é o teste que prova que funcionou de verdade
- Clique de vez em quando em **"💾 Baixar backup"** dentro do app — na nuvem não tem o backup automático diário que criei aqui no PC (o Agendador de Tarefas do Windows não existe lá)
- Combine com você mesmo: depois disso, o financeiro "de verdade" passa a ser o da nuvem — evita ter dois bancos de dados divergentes
