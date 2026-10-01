/**
 * Registro de acesso — Contabilidade para Formação de Preço (UNEMAT, Câmpus de Sinop)
 *
 * Este script fica numa planilha Google do professor e faz três coisas:
 *   1. Login: o acadêmico entra com a conta institucional (@unemat.br) e, no
 *      primeiro acesso, informa nome completo, matrícula e curso (aba Cadastro).
 *   2. Registro: o site envia cada acesso (entrada, páginas visitadas,
 *      exercícios liberados) para a aba Acessos.
 *   3. Estatísticas: a aba Resumo mostra a frequência por acadêmico, por dia,
 *      por página e por curso, e quem da turma ainda não acessou.
 *
 * Instalação: veja acesso/PASSO-A-PASSO.md no repositório do site.
 */

const CONFIG = {
  dominios: ['unemat.br'],                                   // contas aceitas no login
  site: 'https://cleitonfranco74.github.io/formacao-de-preco/',
  validadeDias: 180,                                         // depois disso, o acadêmico entra de novo
  cursos: ['Ciências Contábeis', 'PROFNIT', 'Outro'],
};

const CABECALHOS = {
  Cadastro: ['E-mail', 'Nome completo', 'Matrícula', 'Curso', 'Cadastrado em', 'Atualizado em'],
  Acessos: ['Data e hora', 'E-mail', 'Nome completo', 'Matrícula', 'Curso', 'Evento', 'Página', 'Detalhe'],
  Turma: ['E-mail', 'Nome completo (opcional)'],
};

// ---------------------------------------------------------------- instalação

/** Rode UMA vez pelo editor (botão Executar) para preparar a planilha. */
function configurar() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Abra o editor pela planilha: Extensões > Apps Script.');
  const props = PropertiesService.getScriptProperties();
  props.setProperty('PLANILHA', ss.getId());
  if (!props.getProperty('SEGREDO')) props.setProperty('SEGREDO', Utilities.getUuid() + Utilities.getUuid());
  Object.keys(CABECALHOS).forEach(function (nome) { criarAba_(ss, nome, CABECALHOS[nome]); });
  if (!ss.getSheetByName('Resumo')) ss.insertSheet('Resumo', 0);
  // estatísticas atualizadas a cada hora
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'atualizarResumo') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('atualizarResumo').timeBased().everyHours(1).create();
  atualizarResumo();
}

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Formação de Preço')
    .addItem('Atualizar estatísticas', 'atualizarResumo')
    .addToUi();
}

function criarAba_(ss, nome, cabecalho) {
  const aba = ss.getSheetByName(nome) || ss.insertSheet(nome);
  if (aba.getLastRow() === 0) {
    aba.appendRow(cabecalho);
    aba.setFrozenRows(1);
    aba.getRange(1, 1, 1, cabecalho.length).setFontWeight('bold');
  }
  return aba;
}

function planilha_() {
  return SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('PLANILHA'));
}

// ---------------------------------------------------------------- login e cadastro

/** Página de login (implantação "Qualquer pessoa na UNEMAT"). */
function doGet(e) {
  const email = emailAtual_();
  const permitido = dominioOk_(email);
  const cadastro = permitido ? buscar_(email) : null;
  const t = HtmlService.createTemplateFromFile('Login');
  t.email = email;
  t.permitido = permitido;
  t.dominio = CONFIG.dominios[0];
  t.nome = cadastro ? cadastro.nome : '';
  t.token = cadastro ? gerarToken_(email) : '';
  t.volta = voltaSegura_(e && e.parameter && e.parameter.volta);
  t.cursos = CONFIG.cursos;
  return t.evaluate()
    .setTitle('Acesso · Contabilidade para Formação de Preço')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Chamado pelo formulário da página de login (google.script.run). */
function cadastrar(dados) {
  const email = emailAtual_();
  if (!dominioOk_(email)) throw new Error('Entre com a sua conta institucional @' + CONFIG.dominios[0] + '.');
  dados = dados || {};
  const nome = limpar_(dados.nome, 120), matricula = limpar_(dados.matricula, 30), curso = limpar_(dados.curso, 40);
  if (nome.split(' ').length < 2) throw new Error('Informe o nome completo.');
  if (!matricula) throw new Error('Informe a matrícula.');
  if (CONFIG.cursos.indexOf(curso) < 0) throw new Error('Escolha o curso.');
  if (dados.consentimento !== true) throw new Error('Para continuar, é preciso concordar com o registro dos dados.');
  const trava = LockService.getScriptLock();
  trava.waitLock(10000);
  try {
    const aba = planilha_().getSheetByName('Cadastro'), atual = buscar_(email), agora = new Date();
    const linha = [email, nome, matricula, curso, atual ? atual.cadastradoEm : agora, agora];
    if (atual) aba.getRange(atual.linha, 1, 1, linha.length).setValues([linha]);
    else aba.appendRow(linha);
  } finally {
    trava.releaseLock();
  }
  return { token: gerarToken_(email), nome: nome };
}

// ---------------------------------------------------------------- registro dos acessos

/** Recebe os acessos enviados pelo site (implantação "Qualquer pessoa"). */
function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    const email = validarToken_(d.token);
    if (!email) return resposta_('acesso inválido');
    const c = buscar_(email);
    if (!c) return resposta_('sem cadastro');
    planilha_().getSheetByName('Acessos').appendRow([new Date(), email, c.nome, c.matricula, c.curso,
      limpar_(d.evento, 30), limpar_(d.pagina, 100), limpar_(d.detalhe, 150)]);
    return resposta_('ok');
  } catch (err) {
    return resposta_('erro');
  }
}

function resposta_(texto) {
  return ContentService.createTextOutput(texto).setMimeType(ContentService.MimeType.TEXT);
}

// ---------------------------------------------------------------- estatísticas

/** Monta a aba Resumo. Roda a cada hora e pelo menu Formação de Preço. */
function atualizarResumo() {
  const ss = planilha_(), fuso = ss.getSpreadsheetTimeZone();
  const dia = function (d) { return Utilities.formatDate(d, fuso, 'yyyy-MM-dd'); };
  const cadastro = linhas_(ss.getSheetByName('Cadastro'));
  const acessos = linhas_(ss.getSheetByName('Acessos'));
  const turma = linhas_(ss.getSheetByName('Turma'));

  const alunos = {};
  cadastro.forEach(function (r) {
    alunos[String(r[0]).toLowerCase()] = { nome: r[1], matricula: r[2], curso: r[3], entradas: 0,
      dias: {}, ultimo: null, paginas: {}, exercicios: {} };
  });
  const porDia = {}, porPagina = {};
  acessos.forEach(function (r) {
    const quando = new Date(r[0]), email = String(r[1]).toLowerCase(), evento = r[5], pagina = r[6];
    const a = alunos[email];
    if (!a || isNaN(quando)) return;
    if (!a.ultimo || quando > a.ultimo) a.ultimo = quando;
    if (evento === 'entrada') {
      a.entradas++;
      a.dias[dia(quando)] = true;
      const d = porDia[dia(quando)] = porDia[dia(quando)] || { entradas: 0, alunos: {} };
      d.entradas++;
      d.alunos[email] = true;
    } else if (evento === 'pagina') {
      a.paginas[pagina] = true;
      const p = porPagina[pagina] = porPagina[pagina] || { vistas: 0, alunos: {} };
      p.vistas++;
      p.alunos[email] = true;
    } else if (evento === 'exercicio liberado') {
      a.exercicios[pagina] = true;
    }
  });

  const n = function (o) { return Object.keys(o).length; };
  const blocos = [];
  blocos.push({
    titulo: 'Frequência por acadêmico',
    cab: ['Nome completo', 'Matrícula', 'Curso', 'E-mail', 'Acessos', 'Dias com acesso', 'Último acesso', 'Páginas diferentes', 'Exercícios liberados'],
    linhas: Object.keys(alunos).map(function (email) {
      const a = alunos[email];
      return [a.nome, a.matricula, a.curso, email, a.entradas, n(a.dias), a.ultimo || '', n(a.paginas), n(a.exercicios)];
    }).sort(function (x, y) { return String(x[0]).localeCompare(String(y[0]), 'pt-BR'); }),
  });
  blocos.push({
    titulo: 'Acessos por dia',
    cab: ['Data', 'Acessos', 'Acadêmicos diferentes'],
    linhas: Object.keys(porDia).sort().reverse().map(function (d) {
      return [d.split('-').reverse().join('/'), porDia[d].entradas, n(porDia[d].alunos)];
    }),
  });
  blocos.push({
    titulo: 'Páginas mais visitadas',
    cab: ['Página', 'Visitas', 'Acadêmicos diferentes'],
    linhas: Object.keys(porPagina).map(function (p) { return [p, porPagina[p].vistas, n(porPagina[p].alunos)]; })
      .sort(function (x, y) { return y[1] - x[1]; }),
  });
  const cursos = {};
  Object.keys(alunos).forEach(function (email) {
    const a = alunos[email], c = cursos[a.curso] = cursos[a.curso] || [0, 0];
    c[0]++;
    c[1] += a.entradas;
  });
  blocos.push({
    titulo: 'Por curso',
    cab: ['Curso', 'Cadastrados', 'Acessos'],
    linhas: Object.keys(cursos).sort().map(function (c) { return [c, cursos[c][0], cursos[c][1]]; }),
  });
  if (turma.length) {
    blocos.push({
      titulo: 'Turma: ainda não acessaram',
      cab: ['E-mail', 'Nome completo'],
      linhas: turma.filter(function (r) {
        const a = alunos[String(r[0]).trim().toLowerCase()];
        return r[0] && (!a || a.entradas === 0);
      }).map(function (r) { return [r[0], r[1] || '']; }),
    });
  }

  const aba = ss.getSheetByName('Resumo') || ss.insertSheet('Resumo', 0);
  aba.clear();
  aba.getRange(1, 1).setValue('Atualizado em ' + Utilities.formatDate(new Date(), fuso, 'dd/MM/yyyy HH:mm') +
    ' · ' + Object.keys(alunos).length + ' acadêmicos cadastrados').setFontWeight('bold');
  let linha = 3;
  blocos.forEach(function (b) {
    aba.getRange(linha, 1).setValue(b.titulo).setFontWeight('bold').setFontSize(12);
    aba.getRange(linha + 1, 1, 1, b.cab.length).setValues([b.cab]).setFontWeight('bold').setBackground('#e8f0ea');
    const corpo = b.linhas.length ? b.linhas : [['(nenhum registro)'].concat(new Array(b.cab.length - 1).fill(''))];
    aba.getRange(linha + 2, 1, corpo.length, b.cab.length).setValues(corpo);
    linha += corpo.length + 4;
  });
  aba.getRange('G:G').setNumberFormat('dd/MM/yyyy HH:mm');
  aba.autoResizeColumns(1, 9);
}

function linhas_(aba) {
  if (!aba || aba.getLastRow() < 2) return [];
  return aba.getRange(2, 1, aba.getLastRow() - 1, aba.getLastColumn()).getValues();
}

// ---------------------------------------------------------------- utilidades

function emailAtual_() {
  return String(Session.getActiveUser().getEmail() || '').toLowerCase();
}

function dominioOk_(email) {
  return !!email && CONFIG.dominios.some(function (d) { return email.slice(-(d.length + 1)) === '@' + d; });
}

function buscar_(email) {
  const valores = linhas_(planilha_().getSheetByName('Cadastro'));
  for (let i = 0; i < valores.length; i++) {
    if (String(valores[i][0]).toLowerCase() === email) {
      return { linha: i + 2, nome: valores[i][1], matricula: valores[i][2], curso: valores[i][3], cadastradoEm: valores[i][4] };
    }
  }
  return null;
}

/** Texto limpo, curto e sem fórmulas (um "=" no início viraria fórmula na planilha). */
function limpar_(valor, max) {
  const s = String(valor == null ? '' : valor).replace(/\s+/g, ' ').trim().slice(0, max);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

/** Só volta para o endereço do site (evita redirecionar para outro lugar). */
function voltaSegura_(volta) {
  const v = String(volta || '');
  return v.indexOf(CONFIG.site) === 0 && !/["'<>\s]/.test(v) ? v.split('#')[0] : CONFIG.site;
}

// Token de acesso: "e-mail|validade" assinado com HMAC-SHA256 e um segredo guardado no script.
function gerarToken_(email) {
  const dados = Utilities.base64EncodeWebSafe(email + '|' + (Date.now() + CONFIG.validadeDias * 864e5));
  return dados + '.' + assinar_(dados);
}

function assinar_(dados) {
  const segredo = PropertiesService.getScriptProperties().getProperty('SEGREDO');
  return Utilities.base64EncodeWebSafe(Utilities.computeHmacSha256Signature(dados, segredo));
}

function validarToken_(token) {
  const partes = String(token || '').split('.');
  if (partes.length !== 2 || assinar_(partes[0]) !== partes[1]) return null;
  const texto = Utilities.newBlob(Utilities.base64DecodeWebSafe(partes[0])).getDataAsString().split('|');
  return Number(texto[1]) > Date.now() && dominioOk_(texto[0]) ? texto[0] : null;
}
