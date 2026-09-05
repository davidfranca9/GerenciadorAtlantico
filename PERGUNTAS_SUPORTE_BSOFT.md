# Perguntas para o suporte Bsoft — integração fiscal via API

**Cliente:** Atlântico Fertlog (`atlanticofertlog.bsoft.app`)
**Contexto:** já usamos a API para cadastro de pessoas e veículos. Queremos que nosso
sistema interno acompanhe o ciclo NF-e → CT-e → Contrato de Frete → CIOT → MDF-e.
Já lemos a documentação em docs.bsoft.app; as perguntas abaixo são o que ela **não** cobre.

---

## Bloco 1 — CT-e

**1.1** O `POST /transporte/v1/conhecimentos/viaNFe` apenas **cadastra** o conhecimento no TMS,
ou também **transmite** o CT-e à SEFAZ? Se apenas cadastra, qual endpoint transmite?

**1.2** Com o `codConhecimentos` retornado, como consultamos **status fiscal, chave de acesso,
protocolo de autorização e motivo de rejeição**? O `GET /transporte/v1/conhecimentos/{id}`
retorna esses campos?

**1.3** Existe endpoint para **reenviar/retransmitir** um CT-e que ficou em rejeição?

**1.4** Existe endpoint para **cancelamento** de CT-e e para **Carta de Correção (CC-e)**?

**1.5** O campo `rascunho: "S"` cria o CT-e **sem nenhum efeito fiscal** (sem transmitir à SEFAZ)?
Existe endpoint para depois autorizar um rascunho?

**1.6** O `GET /transporte/v1/paramCriaCteViaNFe` retorna vazio (204) na nossa conta.
**Como configuramos um Parâmetro de Criação de CT-e a partir de NF-e?** É tela do sistema
ou configuração feita pelo suporte? Sem ele não conseguimos usar o `viaNFe`.

**1.7** O `regraFrete_id` é obrigatório no `POST /transporte/v1/conhecimentos`, mas não
encontramos endpoint que liste as regras de frete. Como obtemos esse id por API?

---

## Bloco 2 — CIOT (o ponto mais crítico para nós)

**2.1** O `POST /transporte/v1/contratosFrete` **dispara a geração do CIOT** na Efrete,
ou o campo `CIOT` apenas **registra** um CIOT já obtido por outro meio?

**2.2** Se não dispara: existe endpoint para **gerar, consultar, cancelar e encerrar** o CIOT?
Procuramos em toda a coleção pública e o termo "CIOT" só aparece como campo de entrada
nos POSTs de CT-e e de contrato de frete.

**2.3** Existe endpoint equivalente à ação de tela **"Contrato de Frete Eletrônico → Incluir"**,
que é o fluxo que hoje gera o CIOT para nós?

**2.4** Para **frota própria**, vocês citam um módulo "CIOT Frota Própria" (sem contrato de frete).
Esse módulo tem API? Como acionamos por integração?

**2.5** Qual o comportamento esperado se criarmos um contrato de frete via API **sem** informar
o CIOT — o contrato fica pendente de CIOT, ou é criado definitivamente sem ele?

---

## Bloco 3 — MDF-e

**3.1** Existe endpoint para **criar e transmitir um MDF-e novo** a partir de CT-es?
Na documentação encontramos apenas importação por XML (`/manifestos/viaXML`), consulta
e as ações `fechar`, `encerrar` e `reabrir`.

**3.2** Como **vincular o CIOT** (e o CPF/CNPJ do responsável) ao MDF-e por API?
Considerando a rejeição **684** por MDF-e sem CIOT a partir de 23/11/2026.

**3.3** O `GET /transporte/v1/parametroCriacaoManifesto` também retorna vazio na nossa conta.
Precisa ser configurado? Como?

---

## Bloco 4 — Confiabilidade da integração

**4.1** Quais chamadas produzem **efeito fiscal real** e quais criam apenas rascunho?

**4.2** Existe **idempotência** (chave de idempotência ou dedupe) nos POSTs de criação?
Em caso de **timeout**, qual o procedimento recomendado para descobrir se o documento
foi criado, antes de tentar novamente?

**4.3** Quais os limites de **timeout, rate limit e repetição** da API?

**4.4** Existe **ambiente de homologação/sandbox** para testarmos a integração sem gerar
documento fiscal real?

---

## Bloco 5 — Reforma tributária

**5.1** Como preencher **CST, classificação tributária, CBS e IBS** na API atual?
Há previsão de mudança de layout na API por conta da reforma?

---

### Observação sobre o que já resolvemos sozinhos
Não é necessário responder: já mapeamos por API os ids de agência (2), talões
(CT-e = 3, MDF-e = 7, Recibo de frete = 5), naturezas de carga e de operação, espécies,
apólices e conjuntos de veículos. Também já confirmamos que as listagens exigem o
parâmetro `fim` (máximo 100) e que cadastro vazio responde 204.
