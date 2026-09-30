"""Protege com senha os gabaritos dos exercícios do site.

O GitHub Pages só serve arquivos estáticos, então a senha não é conferida por
um servidor: o gabarito é CRIPTOGRAFADO (AES-256-GCM, chave derivada da senha
por PBKDF2-SHA256) e o navegador só consegue decifrá-lo com a senha certa.
Cada exercício tem a SUA senha: a senha de um não abre o gabarito de outro.

O que o script faz, para cada exercício listado em PROTEGER:
  1. troca o "Gabarito comentado" do index.html por um bloco cifrado com um
     campo de senha;
  2. cifra o gabarito .docx em arquivos/<nome>.docx.enc, APAGA o .docx original
     e troca os links de download por botões que pedem a senha;
  3. cifra os dados do exercício usados pelo simulador e pela calculadora de
     preço (que resolveriam o exercício). Essas ferramentas passam a abrir com
     uma empresa-exemplo livre (EXEMPLO) e liberam cada exercício com a senha dele.

Uso (rode depois de gerar o site, a partir da raiz do repositório):
    python ferramentas/proteger_gabaritos.py
As senhas ficam em senhas_gabaritos.json, na raiz do repositório. Se o arquivo
não existir, o script cria senhas novas e as grava nele. Esse arquivo está no
.gitignore: NUNCA o envie ao GitHub (o repositório é público).
Guarde uma cópia dos .docx originais: o script os remove da pasta arquivos/.

Requer: pip install cryptography
"""

import base64
import json
import os
import re
import secrets
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")
PASTA = os.path.join(RAIZ, "arquivos")
ITERACOES = 600_000
SENHAS = os.path.join(RAIZ, "senhas_gabaritos.json")

# id da seção do exercício -> gabarito .docx correspondente
PROTEGER = {
    "agroindustria-grao-dourado-p1": "Agroindustria_Grao_Dourado_Custos_MC_Gabarito.docx",
    "agroindustria-grao-dourado-p2": "Agroindustria_Grao_Dourado_Custeio_Absorcao_Gabarito.docx",
    "cervejaria-serra-azul-p1": "Cervejaria_Serra_Azul_Custos_MC_Gabarito.docx",
    "cervejaria-serra-azul-p2": "Cervejaria_Serra_Azul_Custeio_Absorcao_Gabarito.docx",
    "usina-milho-ouro-bioenergia-p1": "Usina_Milho_Ouro_Custos_MC_Gabarito.docx",
    "usina-milho-ouro-bioenergia-p2": "Usina_Milho_Ouro_Custeio_Absorcao_Gabarito.docx",
    "confeccoes-serra-do-cerrado-p1": "Confeccoes_Serra_do_Cerrado_Custos_MC_Gabarito.docx",
    "confeccoes-serra-do-cerrado-p2": "Confeccoes_Serra_do_Cerrado_Custeio_Absorcao_Gabarito.docx",
    "metalurgica-portal-do-cerrado-p1": "Metalurgica_Portal_do_Cerrado_Custos_MC_Gabarito.docx",
    "metalurgica-portal-do-cerrado-p2": "Metalurgica_Portal_do_Cerrado_Custeio_Absorcao_Gabarito.docx",
    "panificadora-trigo-dourado-p1": "Panificadora_Trigo_Dourado_Custos_MC_Gabarito.docx",
    "panificadora-trigo-dourado-p2": "Panificadora_Trigo_Dourado_Custeio_Absorcao_Gabarito.docx",
    "plasticos-vale-do-teles-pires-p1": "Plasticos_Vale_do_Teles_Pires_Custos_MC_Gabarito.docx",
    "plasticos-vale-do-teles-pires-p2": "Plasticos_Vale_do_Teles_Pires_Custeio_Absorcao_Gabarito.docx",
    "laticinios-nortao-p3": "Laticinios_Nortao_Formacao_Precos_Gabarito.docx",
    "moveis-portal-da-amazonia-p3": "Moveis_Portal_da_Amazonia_Formacao_Precos_Gabarito.docx",
    "racoes-cerrado-forte-p3": "Racoes_Cerrado_Forte_Formacao_Precos_Gabarito.docx",
}

FORMULARIO = """<div class="cadeado" data-secao="{secao}" data-cifra="{cifra}">
        <p>Este gabarito é protegido por senha. Informe a senha deste exercício, fornecida pelo professor.</p>
        <form class="desbloquear">
          <input type="password" autocomplete="current-password" aria-label="Senha do gabarito" placeholder="Senha do gabarito" required>
          <button type="submit" class="btn peq">Desbloquear</button>
        </form>
        <p class="erro" aria-live="polite"></p>
      </div>"""

# empresa fictícia, sempre liberada no simulador e na calculadora
EXEMPLO = {
    "empresa": "Sorvetes Ipê Amarelo (exemplo)", "tipo": "mc", "base2": "MOD",
    "produtos": [
        {"nome": "Picolé", "un": "un.", "volume": 300000, "preco": 3.0, "comissao": 0.05,
         "frete": 0.10, "embalagem": 0.05, "base2": 0.01, "cvu": 0.90},
        {"nome": "Pote de sorvete 2 L", "un": "pote", "volume": 60000, "preco": 28.0, "comissao": 0.05,
         "frete": 1.0, "embalagem": 0.80, "base2": 0.10, "cvu": 11.0},
        {"nome": "Açaí 1 L", "un": "pote", "volume": 40000, "preco": 22.0, "comissao": 0.05,
         "frete": 0.80, "embalagem": 0.60, "base2": 0.08, "cvu": 9.5},
    ],
    "cif": 420000, "df": 180000, "markup": None,
    "terceirizacao": {"produto": 2, "valor": 390000},
    "pedido": {"produto": 0, "qtd": 50000, "preco": 2.10},
}
OPCAO_EXEMPLO = ('  <optgroup label="Exemplo · livre">\n'
                 '    <option value="exemplo" selected>Sorvetes Ipê Amarelo (empresa-exemplo)</option>\n'
                 '  </optgroup>\n')

# (trecho original, trecho novo) aplicados às ferramentas interativas
AJUSTES = [
    ('<select id="sim-exercicio">\n', '<select id="sim-exercicio">\n' + OPCAO_EXEMPLO),
    ('<select id="pr-exercicio">\n', '<select id="pr-exercicio">\n' + OPCAO_EXEMPLO),
    ('<p class="lead">Escolha qualquer exercício e produto, ajuste os percentuais e veja o preço sugerido, o preço mínimo e o custo-meta.</p>',
     '<p class="lead">Escolha um exercício e um produto, ajuste os percentuais e veja o preço sugerido, o preço mínimo e o custo-meta. '
     'A empresa-exemplo é livre; os exercícios 🔒 são liberados com a senha do gabarito de cada um.</p>'),
    ('<p class="lead">Escolha qualquer um dos 17 exercícios, mude preços e volumes',
     '<p class="lead">Comece pela empresa-exemplo (os exercícios 🔒 são liberados com a senha do gabarito de cada um), mude preços e volumes'),
    ('  try { MODELO = JSON.parse(document.getElementById("dados-modelo").textContent); } catch (e) {}\n',
     '  try { MODELO = JSON.parse(document.getElementById("dados-modelo").textContent); } catch (e) {}\n'
     '  // exercícios protegidos: os dados chegam cifrados e são liberados com a senha do exercício\n'
     '  // (ver "gabaritos protegidos por senha", no fim da página)\n'
     '  function formModelo(id) {\n'
     '    return \'<div class="cadeado" data-modelo="\' + esc(id) + \'"><p>Os dados deste exercício são liberados com a senha do gabarito dele, \' +\n'
     '      "fornecida pelo professor. Enquanto isso, use a empresa-exemplo.</p>" +\n'
     '      \'<form class="desbloquear"><input type="password" autocomplete="current-password" aria-label="Senha do exercício" placeholder="Senha do exercício" required>\' +\n'
     '      \'<button type="submit" class="btn peq">Desbloquear</button></form><p class="erro" aria-live="polite"></p></div>\';\n'
     '  }\n'
     '  function marcarBloqueados() {\n'
     '    document.querySelectorAll("#sim-exercicio option, #pr-exercicio option").forEach(function (o) {\n'
     '      o.textContent = o.textContent.replace(/ 🔒$/, "") + (MODELO[o.value] ? "" : " 🔒");\n'
     '    });\n'
     '  }\n'),
    ('    var montar = function () {\n      var ex = MODELO[selSim.value];\n',
     '    var montar = function () {\n      var ex = MODELO[selSim.value];\n'
     '      if (!ex) { campos.innerHTML = ""; saida.innerHTML = formModelo(selSim.value); return; }\n'),
    ('    var simular = function () {\n      var ex = MODELO[selSim.value];\n',
     '    var simular = function () {\n      var ex = MODELO[selSim.value];\n      if (!ex) return;\n'),
    ('window.addEventListener("simulador:exercicio", function (ev) { if (MODELO[ev.detail]) {',
     'window.addEventListener("simulador:exercicio", function (ev) { if ([].some.call(selSim.options, function (o) { return o.value === ev.detail; })) {'),
    ('    var trocarExercicio = function () {\n',
     '    var trocarExercicio = function () {\n'
     '      if (!MODELO[selEx.value]) { selProd.innerHTML = ""; res.innerHTML = formModelo(selEx.value); nota.textContent = ""; return; }\n'),
    ('      var p = MODELO[selEx.value].produtos[+selProd.value];\n',
     '      if (!MODELO[selEx.value]) return;\n      var p = MODELO[selEx.value].produtos[+selProd.value];\n'),
    ('      var ex = MODELO[selEx.value], r = calcular(ex), p = r.ps[+selProd.value];\n',
     '      if (!MODELO[selEx.value]) return;\n      var ex = MODELO[selEx.value], r = calcular(ex), p = r.ps[+selProd.value];\n'),
    ('    trocarExercicio();\n  }\n})();',
     '    trocarExercicio();\n  }\n\n'
     '  // exercício liberado pela senha: entra no simulador e na calculadora\n'
     '  window.addEventListener("modelo:liberado", function (ev) {\n'
     '    MODELO[ev.detail.id] = ev.detail.dados;\n'
     '    marcarBloqueados();\n'
     '    if (sim && selSim.value === ev.detail.id) montar();\n'
     '    if (calc && selEx.value === ev.detail.id) trocarExercicio();\n'
     '  });\n'
     '  marcarBloqueados();\n})();'),
]

CSS = """
/* ---------- gabaritos protegidos por senha ---------- */
.cadeado{display:grid;gap:10px;max-width:460px}
.cadeado p{margin:0}
.cadeado form{display:flex;gap:8px;flex-wrap:wrap}
.cadeado input{flex:1 1 180px;width:auto}
.cadeado .erro:empty{display:none}
.cadeado .erro,.aviso-download.erro{color:var(--crit-text)}
"""

JS = r"""
  // ---------- gabaritos protegidos por senha (gerado por ferramentas/proteger_gabaritos.py) ----------
  // O conteúdo está cifrado (AES-GCM) com uma senha por exercício; a chave é derivada com PBKDF2
  // e fica só na memória.
  var PROTECAO = null;
  try { PROTECAO = JSON.parse(document.getElementById("protecao-gabaritos").textContent); } catch (e) {}
  var chaves = {};   // exercício -> chave já desbloqueada
  function deB64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function derivarChave(senha, salt) {
    return crypto.subtle.importKey("raw", new TextEncoder().encode(senha), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: deB64(salt), iterations: PROTECAO.iter, hash: "SHA-256" },
        base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    });
  }
  function decifrar(chave, bytes) {   // bytes = iv (12) + texto cifrado
    return crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, chave, bytes.slice(12));
  }
  // testa a senha do exercício; se servir, guarda a chave
  function obterChave(secao, senha) {
    if (chaves[secao]) return Promise.resolve(chaves[secao]);
    if (!window.crypto || !crypto.subtle) return Promise.reject(new Error("sem-cripto"));
    var p = PROTECAO.secoes[secao];
    return derivarChave(senha, p.salt).then(function (k) {
      return decifrar(k, deB64(p.teste)).then(function () { chaves[secao] = k; liberarModelo(secao, k); return k; },
        function () { throw new Error("senha"); });
    });
  }
  // dados do exercício para o simulador e a calculadora de preço
  function liberarModelo(secao, chave) {
    var d = PROTECAO.secoes[secao].dados;
    if (!d) return;
    decifrar(chave, deB64(d)).then(function (buf) {
      window.dispatchEvent(new CustomEvent("modelo:liberado", { detail: { id: secao, dados: JSON.parse(new TextDecoder().decode(buf)) } }));
    });
  }
  function abrirGabarito(secao, chave) {
    document.querySelectorAll('.cadeado[data-secao="' + secao + '"]').forEach(function (c) {
      decifrar(chave, deB64(c.getAttribute("data-cifra"))).then(function (buf) {
        var pai = c.parentNode, d = document.createElement("div");
        d.innerHTML = new TextDecoder().decode(buf);
        c.replaceWith.apply(c, Array.prototype.slice.call(d.childNodes));
        ligar(pai);
      });
    });
  }
  function msgErro(e) {
    return e && e.message === "senha" ? "Senha incorreta para este exercício."
      : "Este navegador não permite abrir o gabarito (use a versão publicada, em https).";
  }
  if (PROTECAO) {
    document.addEventListener("submit", function (ev) {
      var f = ev.target.closest && ev.target.closest("form.desbloquear");
      if (!f) return;
      ev.preventDefault();
      var secao = f.parentNode.getAttribute("data-secao") || f.parentNode.getAttribute("data-modelo"), erro = f.parentNode.querySelector(".erro"), bt = f.querySelector("button");
      bt.disabled = true; erro.textContent = "";
      obterChave(secao, f.querySelector("input").value).then(function (k) { abrirGabarito(secao, k); },
        function (e) { erro.textContent = msgErro(e); })
        .then(function () { bt.disabled = false; });
    });
    document.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest("button.baixar-protegido");
      if (!b) return;
      var secao = b.getAttribute("data-secao"), nome = b.getAttribute("data-nome");
      var senha = chaves[secao] ? "" : window.prompt("Senha do gabarito deste exercício:");
      if (senha === null) return;
      b.disabled = true;
      obterChave(secao, senha).then(function (k) {
        abrirGabarito(secao, k);
        return fetch(b.getAttribute("data-enc")).then(function (r) {
          if (!r.ok) throw new Error("arquivo");
          return r.arrayBuffer();
        }).then(function (buf) { return decifrar(k, new Uint8Array(buf)); }).then(function (docx) {
          var a = document.createElement("a");
          a.href = URL.createObjectURL(new Blob([docx], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }));
          a.download = nome; document.body.appendChild(a); a.click(); a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 10000);
          aviso(b, "");
        }, function () { throw new Error("arquivo"); });
      }).catch(function (e) {
        aviso(b, e.message === "arquivo" ? "Não foi possível baixar o arquivo." : msgErro(e));
        b.parentNode.querySelector(".aviso-download.dinamico").classList.add("erro");
      }).then(function () { b.disabled = false; });
    });
  }
"""


def b64(dados):
    return base64.b64encode(dados).decode("ascii")


def nova_senha():
    """Variação do modelo Qco2h94@#$: "Qco" + 4 letras/números + 3 símbolos, sorteados."""
    alfanum = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    simbolos = "@#$%&*!?"
    return ("Qco" + "".join(secrets.choice(alfanum) for _ in range(4))
            + "".join(secrets.choice(simbolos) for _ in range(3)))


def carregar_senhas():
    senhas = {}
    if os.path.exists(SENHAS):
        with open(SENHAS, encoding="utf-8") as f:
            senhas = json.load(f)
    novas = [s for s in PROTEGER if s not in senhas]
    for secao in novas:
        senhas[secao] = nova_senha()
    if novas:
        with open(SENHAS, "w", encoding="utf-8") as f:
            json.dump(senhas, f, ensure_ascii=False, indent=2)
        print(f"{len(novas)} senha(s) nova(s) gravada(s) em {SENHAS}")
    return senhas


def main():
    html = open(INDEX, encoding="utf-8").read()
    if 'id="protecao-gabaritos"' in html:
        sys.exit("O index.html já está protegido. Gere o site novamente antes de rodar o script.")

    senhas = carregar_senhas()
    params = {"iter": ITERACOES, "secoes": {}}
    m_modelo = re.search(r'(<script type="application/json" id="dados-modelo">)(.*?)(</script>)', html, re.S)
    if not m_modelo:
        sys.exit("Dados do simulador (dados-modelo) não encontrados.")
    modelo = json.loads(m_modelo.group(2))

    for secao, nome in PROTEGER.items():
        salt = os.urandom(16)
        chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                           iterations=ITERACOES).derive(senhas[secao].encode("utf-8"))
        aes = AESGCM(chave)

        def cifrar(dados):
            iv = os.urandom(12)
            return iv + aes.encrypt(iv, dados, None)

        params["secoes"][secao] = {"salt": b64(salt), "teste": b64(cifrar(b"ok"))}
        if secao in modelo:
            dados = json.dumps(modelo.pop(secao), ensure_ascii=False).encode("utf-8")
            params["secoes"][secao]["dados"] = b64(cifrar(dados))

        # 1. gabarito comentado
        padrao = re.compile(
            r'(<section class="bloco cinza" id="' + re.escape(secao) + r'-gabarito">.*?<div class="corpo doc">\n)(.*?)(\n\s*</div>\n\s*</details>)',
            re.S)
        m = padrao.search(html)
        if not m:
            sys.exit(f"Gabarito comentado não encontrado: {secao}")
        bloco = FORMULARIO.format(secao=secao, cifra=b64(cifrar(m.group(2).encode("utf-8"))))
        html = html[:m.start(2)] + "      " + bloco + html[m.end(2):]

        # 2. arquivo .docx
        caminho = os.path.join(PASTA, nome)
        with open(caminho, "rb") as f:
            dados = f.read()
        with open(caminho + ".enc", "wb") as f:
            f.write(cifrar(dados))
        os.remove(caminho)
        link = re.compile(r'<a class="btn sec peq" href="arquivos/' + re.escape(nome) + r'" download>(.*?)</a>')
        html, n = link.subn(
            lambda m: f'<button type="button" class="btn sec peq baixar-protegido" data-secao="{secao}" '
                      f'data-enc="arquivos/{nome}.enc" data-nome="{nome}">{m.group(1)} 🔒</button>', html)
        print(f"cifrado: {secao} (gabarito comentado + {nome}, {n} links)")

    # 3. simulador e calculadora: só a empresa-exemplo fica aberta
    modelo = {"exemplo": EXEMPLO, **modelo}
    html = html.replace(m_modelo.group(0), m_modelo.group(1) + json.dumps(modelo, ensure_ascii=False) + m_modelo.group(3), 1)
    for antigo, novo in AJUSTES:
        if html.count(antigo) != 1:
            sys.exit(f"Trecho das ferramentas não encontrado (ou repetido): {antigo[:60]!r}")
        html = html.replace(antigo, novo, 1)

    # 4. parâmetros, estilo e script
    html = html.replace('<script type="application/json" id="dados-modelo">',
                        '<script type="application/json" id="protecao-gabaritos">' + json.dumps(params) + '</script>\n'
                        '<script type="application/json" id="dados-modelo">', 1)
    html = html.replace("\n/* ---------- formulários ---------- */", CSS + "\n/* ---------- formulários ---------- */", 1)
    html = html.replace("\n  // ---------- navegação por abas (hash) ----------", JS + "\n  // ---------- navegação por abas (hash) ----------", 1)
    for trecho in ('id="protecao-gabaritos"', ".cadeado{", "abrirGabarito"):
        if trecho not in html:
            sys.exit(f"Não consegui inserir {trecho!r} — a estrutura do index.html mudou.")

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)
    print("Pronto.")


if __name__ == "__main__":
    main()
