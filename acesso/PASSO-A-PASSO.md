# Registro de acesso: passo a passo

Este guia instala o cadastro e o registro de acesso do site
<https://cleitonfranco74.github.io/formacao-de-preco/>.

**Como funciona:**
- O acadêmico abre o site e entra com a conta institucional **@unemat.br**.
- No primeiro acesso, informa **nome completo, matrícula e curso**.
- Cada entrada, página visitada e exercício liberado com senha vai para uma **planilha Google sua**.
- A aba **Resumo** dessa planilha mostra as estatísticas, atualizadas a cada hora.

Tempo estimado: 15 minutos. Use **sempre a sua conta @unemat.br**.

---

## 1. Criar a planilha

1. Entre no Google Drive com a conta **@unemat.br**.
2. Clique em **Novo > Planilhas Google** e dê o nome **Acessos – Formação de Preço**.

## 2. Colar o código

1. Na planilha, abra o menu **Extensões > Apps Script**. O editor abre numa nova aba.
2. No arquivo **Código.gs**, apague tudo e cole o conteúdo de
   [`acesso/Codigo.gs`](Codigo.gs).
3. Crie a página de login: clique no **+** ao lado de "Arquivos" e escolha **HTML**.
   Dê o nome **Login**, exatamente assim (o editor completa com `.html`).
   Apague o conteúdo e cole o de [`acesso/Login.html`](Login.html).
4. Clique em **Salvar** (ícone de disquete).

## 3. Preparar a planilha (uma vez só)

1. Na barra do editor, escolha a função **configurar** e clique em **Executar**.
2. O Google pede autorização:
   - clique em **Revisar permissões** e escolha a sua conta @unemat.br;
   - se aparecer "O Google não verificou este app", clique em **Avançado** e depois em
     **Acessar (não seguro)**. O app é o seu próprio script;
   - clique em **Permitir**.
3. Volte à planilha. Devem aparecer as abas **Resumo, Cadastro, Acessos e Turma**.

## 4. Publicar o login (implantação 1)

1. No editor, clique em **Implantar > Nova implantação**.
2. Na engrenagem de "Selecionar tipo", escolha **App da Web**.
3. Preencha:
   - **Descrição:** Login
   - **Executar como:** Eu
   - **Quem pode acessar:** **Qualquer pessoa em UNEMAT** (ou o nome do domínio da universidade)
4. Clique em **Implantar** e copie o **URL do app da Web**, que termina em `/exec`.
   Esse é o **endereço de LOGIN**.

## 5. Publicar o registro (implantação 2)

1. Clique de novo em **Implantar > Nova implantação** e escolha **App da Web**.
2. Preencha:
   - **Descrição:** Registro
   - **Executar como:** Eu
   - **Quem pode acessar:** **Qualquer pessoa**
3. Clique em **Implantar** e copie o URL. Esse é o **endereço de REGISTRO**.

> As duas implantações usam o mesmo código. Elas são separadas porque o login precisa
> exigir a conta UNEMAT, enquanto o registro recebe os acessos enviados pelo site.
> O registro só aceita envios com um código de acesso assinado, gerado no login, então
> ninguém consegue registrar acessos em nome de outra pessoa.

## 6. Ativar no site

Envie os dois endereços (LOGIN e REGISTRO) para o Claude, que coloca no site.

Se preferir fazer você mesmo, abra o `index.html` e preencha a linha:

```js
window.ACESSO = { login: "", registro: "" };
```

Até esses endereços serem preenchidos, o site funciona normalmente, sem pedir login.

## 7. Testar

1. Abra o site numa **janela anônima** (Ctrl+Shift+N).
2. Clique em **Entrar com a conta UNEMAT**, entre com uma conta @unemat.br e faça o cadastro.
3. Navegue por algumas páginas.
4. Na planilha, confira as abas **Cadastro** e **Acessos** e, no menu
   **Formação de Preço > Atualizar estatísticas**, a aba **Resumo**.

---

## Usando no dia a dia

- **Estatísticas:** aba **Resumo**, com frequência por acadêmico (acessos, dias com acesso,
  último acesso, páginas e exercícios liberados), acessos por dia, páginas mais visitadas e
  totais por curso. A aba se atualiza sozinha a cada hora. Para atualizar na hora, use o menu
  **Formação de Preço > Atualizar estatísticas**.
- **Quem não acessou:** cole na aba **Turma** os e-mails @unemat.br dos matriculados (coluna A)
  e, se quiser, os nomes (coluna B). O Resumo passa a listar quem ainda não acessou.
- **Dados brutos:** a aba **Acessos** tem uma linha por evento. Use filtros ou tabela dinâmica
  para outras análises.
- **Novo semestre (LGPD):** a tela de cadastro informa que os dados são apagados ao fim do
  semestre. No encerramento, apague as linhas (exceto o cabeçalho) das abas **Cadastro**,
  **Acessos** e **Turma**.

## Se algo der errado

- **"Qualquer pessoa em UNEMAT" ou "Qualquer pessoa" não aparece** em "Quem pode acessar": a
  administração do Google da UNEMAT pode ter bloqueado essa opção. Fale com o suporte de TI ou
  avise o Claude para procurar outra solução.
- **O aluno vê "Você precisa de permissão" ou é recusado:** ele entrou com uma conta pessoal
  (@gmail.com). Peça para sair e entrar com a conta @unemat.br. A página de login também tem
  o botão **Trocar de conta**.
- **Alterou o código:** em **Implantar > Gerenciar implantações**, edite **cada uma** das duas
  implantações (ícone de lápis), escolha **Nova versão** e clique em **Implantar**. Os
  endereços continuam os mesmos.

## Limites

- O login confirma o e-mail institucional. Nome, matrícula e curso são informados pelo
  próprio acadêmico.
- A tela de entrada impede o uso comum sem login, mas o conteúdo está no próprio site. Alguém
  com conhecimento técnico consegue contorná-la. Quem fizer isso não aparece nas estatísticas.
  Os gabaritos continuam protegidos pelas senhas de cada exercício.
- O acesso vale por 180 dias no mesmo navegador. Depois disso, ou em outro navegador, o
  acadêmico entra de novo.
