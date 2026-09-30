"""Protege com senha os gabaritos das empresas novas do site.

O GitHub Pages só serve arquivos estáticos, então a senha não é conferida por
um servidor: o gabarito é CRIPTOGRAFADO (AES-256-GCM, chave derivada da senha
por PBKDF2-SHA256) e o navegador só consegue decifrá-lo com a senha certa.

O que o script faz, para cada exercício listado em PROTEGER:
  1. troca o "Gabarito comentado" do index.html por um bloco cifrado com um
     campo de senha;
  2. cifra o gabarito .docx em arquivos/<nome>.docx.enc, APAGA o .docx original
     e troca os links de download por botões que pedem a senha.

Uso (rode depois de gerar o site, a partir da raiz do repositório):
    python ferramentas/proteger_gabaritos.py
A senha é pedida no terminal (ou lida da variável de ambiente GABARITO_SENHA).
Guarde uma cópia dos .docx originais: o script os remove da pasta arquivos/.

Requer: pip install cryptography
"""

import base64
import getpass
import json
import os
import re
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")
PASTA = os.path.join(RAIZ, "arquivos")
ITERACOES = 600_000

# id da seção do exercício -> gabarito .docx correspondente
PROTEGER = {
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

FORMULARIO = """<div class="cadeado" data-cifra="{cifra}">
        <p>Este gabarito é protegido por senha. Informe a senha fornecida pelo professor.</p>
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
  // O conteúdo está cifrado (AES-GCM); a chave é derivada da senha com PBKDF2 e fica só na memória.
  var PROTECAO = null;
  try { PROTECAO = JSON.parse(document.getElementById("protecao-gabaritos").textContent); } catch (e) {}
  var chaveGabarito = null;
  function deB64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function derivarChave(senha) {
    return crypto.subtle.importKey("raw", new TextEncoder().encode(senha), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: deB64(PROTECAO.salt), iterations: PROTECAO.iter, hash: "SHA-256" },
        base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    });
  }
  function decifrar(chave, bytes) {   // bytes = iv (12) + texto cifrado
    return crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, chave, bytes.slice(12));
  }
  // testa a senha no primeiro bloco cifrado; se servir, guarda a chave
  function obterChave(senha) {
    if (chaveGabarito) return Promise.resolve(chaveGabarito);
    if (!window.crypto || !crypto.subtle) return Promise.reject(new Error("sem-cripto"));
    return derivarChave(senha).then(function (k) {
      return decifrar(k, deB64(PROTECAO.teste)).then(function () { chaveGabarito = k; return k; },
        function () { throw new Error("senha"); });
    });
  }
  function abrirGabaritos(chave) {
    document.querySelectorAll(".cadeado[data-cifra]").forEach(function (c) {
      decifrar(chave, deB64(c.getAttribute("data-cifra"))).then(function (buf) {
        var pai = c.parentNode, d = document.createElement("div");
        d.innerHTML = new TextDecoder().decode(buf);
        c.replaceWith.apply(c, Array.prototype.slice.call(d.childNodes));
        ligar(pai);
      });
    });
  }
  function msgErro(e) {
    return e && e.message === "senha" ? "Senha incorreta."
      : "Este navegador não permite abrir o gabarito (use a versão publicada, em https).";
  }
  if (PROTECAO) {
    document.addEventListener("submit", function (ev) {
      var f = ev.target.closest && ev.target.closest("form.desbloquear");
      if (!f) return;
      ev.preventDefault();
      var erro = f.parentNode.querySelector(".erro"), bt = f.querySelector("button");
      bt.disabled = true; erro.textContent = "";
      obterChave(f.querySelector("input").value).then(abrirGabaritos, function (e) { erro.textContent = msgErro(e); })
        .then(function () { bt.disabled = false; });
    });
    document.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest("button.baixar-protegido");
      if (!b) return;
      var senha = chaveGabarito ? "" : window.prompt("Senha do gabarito:");
      if (senha === null) return;
      var nome = b.getAttribute("data-nome");
      b.disabled = true;
      obterChave(senha).then(function (k) {
        abrirGabaritos(k);
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


def main():
    html = open(INDEX, encoding="utf-8").read()
    if 'id="protecao-gabaritos"' in html:
        sys.exit("O index.html já está protegido. Gere o site novamente antes de rodar o script.")

    senha = os.environ.get("GABARITO_SENHA") or getpass.getpass("Senha dos gabaritos: ")
    if len(senha) < 8:
        sys.exit("Use uma senha com pelo menos 8 caracteres.")

    salt = os.urandom(16)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACOES).derive(senha.encode("utf-8"))
    aes = AESGCM(chave)

    def cifrar(dados):
        iv = os.urandom(12)
        return iv + aes.encrypt(iv, dados, None)

    # 1. gabaritos comentados
    for secao in PROTEGER:
        padrao = re.compile(
            r'(<section class="bloco cinza" id="' + re.escape(secao) + r'-gabarito">.*?<div class="corpo doc">\n)(.*?)(\n\s*</div>\n\s*</details>)',
            re.S)
        m = padrao.search(html)
        if not m:
            sys.exit(f"Gabarito comentado não encontrado: {secao}")
        bloco = FORMULARIO.format(cifra=b64(cifrar(m.group(2).encode("utf-8"))))
        html = html[:m.start(2)] + "      " + bloco + html[m.end(2):]
        print(f"gabarito comentado cifrado: {secao}")

    # 2. arquivos .docx
    for nome in PROTEGER.values():
        caminho = os.path.join(PASTA, nome)
        with open(caminho, "rb") as f:
            dados = f.read()
        with open(caminho + ".enc", "wb") as f:
            f.write(cifrar(dados))
        os.remove(caminho)
        link = re.compile(r'<a class="btn sec peq" href="arquivos/' + re.escape(nome) + r'" download>(.*?)</a>')
        html, n = link.subn(
            lambda m: f'<button type="button" class="btn sec peq baixar-protegido" data-enc="arquivos/{nome}.enc" '
                      f'data-nome="{nome}">{m.group(1)} 🔒</button>', html)
        print(f"docx cifrado: {nome} ({n} links)")

    # 3. parâmetros, estilo e script
    params = {"salt": b64(salt), "iter": ITERACOES, "teste": b64(cifrar(b"ok"))}
    html = html.replace('<script type="application/json" id="dados-modelo">',
                        '<script type="application/json" id="protecao-gabaritos">' + json.dumps(params) + '</script>\n'
                        '<script type="application/json" id="dados-modelo">', 1)
    html = html.replace("\n/* ---------- formulários ---------- */", CSS + "\n/* ---------- formulários ---------- */", 1)
    html = html.replace("\n  // ---------- navegação por abas (hash) ----------", JS + "\n  // ---------- navegação por abas (hash) ----------", 1)
    for trecho in ('id="protecao-gabaritos"', ".cadeado{", "chaveGabarito"):
        if trecho not in html:
            sys.exit(f"Não consegui inserir {trecho!r} — a estrutura do index.html mudou.")

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)
    print("Pronto.")


if __name__ == "__main__":
    main()
