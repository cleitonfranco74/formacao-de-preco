"""Protege com senha os gabaritos dos exercícios do site.

O GitHub Pages só serve arquivos estáticos, então a senha não é conferida por
um servidor: o gabarito é CRIPTOGRAFADO (AES-256-GCM, chave derivada da senha
por PBKDF2-SHA256) e o navegador só consegue decifrá-lo com a senha certa.
Cada exercício tem a SUA senha: a senha de um não abre o gabarito de outro.

O que o script faz, para cada exercício listado em PROTEGER:
  1. troca o "Gabarito comentado" do index.html por um bloco cifrado com um
     campo de senha;
  2. cifra o gabarito .docx em arquivos/<nome>.docx.enc, APAGA o .docx original
     e troca os links de download por botões que pedem a senha.

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
      return decifrar(k, deB64(p.teste)).then(function () { chaves[secao] = k; return k; },
        function () { throw new Error("senha"); });
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
      var secao = f.parentNode.getAttribute("data-secao"), erro = f.parentNode.querySelector(".erro"), bt = f.querySelector("button");
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

    for secao, nome in PROTEGER.items():
        salt = os.urandom(16)
        chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                           iterations=ITERACOES).derive(senhas[secao].encode("utf-8"))
        aes = AESGCM(chave)

        def cifrar(dados):
            iv = os.urandom(12)
            return iv + aes.encrypt(iv, dados, None)

        params["secoes"][secao] = {"salt": b64(salt), "teste": b64(cifrar(b"ok"))}

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

    # 3. parâmetros, estilo e script
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
