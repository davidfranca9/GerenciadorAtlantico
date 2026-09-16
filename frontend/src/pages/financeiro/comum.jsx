import { useEffect, useRef, useState } from "react";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { brl, diaBr, mudarCompetencia, nomeCompetencia, partesBrl, toneladas } from "./formato";

// Valor com os centavos menores: "R$ 69.358,24".
export function Dinheiro({ valor, tamanho = "m", sinal = false, className = "" }) {
  if (valor === null || valor === undefined) return <span className={`fin-dinheiro ${tamanho} ${className}`}>—</span>;
  const { negativo, inteiro, centavos } = partesBrl(valor);
  const prefixo = negativo ? "−" : sinal && Number(valor) > 0 ? "+" : "";
  return (
    <span className={`fin-dinheiro ${tamanho} ${className}`}>
      <span className="fin-moeda">{prefixo}R$</span>
      <span className="fin-inteiro">{inteiro}</span>
      <span className="fin-centavos">,{centavos}</span>
    </span>
  );
}

export function NavegadorMes({ competencia, aoMudar }) {
  return (
    <div className="fin-nav-periodo">
      <button type="button" className="icon-btn" aria-label="Mês anterior" onClick={() => aoMudar(mudarCompetencia(competencia, -1))}>
        <Icon name="chevron" size={16} className="fin-seta-esquerda" />
      </button>
      <strong>{nomeCompetencia(competencia)}</strong>
      <button type="button" className="icon-btn" aria-label="Próximo mês" onClick={() => aoMudar(mudarCompetencia(competencia, 1))}>
        <Icon name="chevron" size={16} />
      </button>
    </div>
  );
}

export function Modal({ titulo, subtitulo, aoFechar, children, largura = 620 }) {
  useEffect(() => {
    const tecla = (e) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [aoFechar]);
  return (
    <div className="fin-modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <div className="fin-modal" role="dialog" aria-modal="true" aria-label={titulo} style={{ maxWidth: largura }}>
        <header>
          <div>
            <h2>{titulo}</h2>
            {subtitulo && <p>{subtitulo}</p>}
          </div>
          <button type="button" className="icon-btn" aria-label="Fechar" onClick={aoFechar}><Icon name="close" size={16} /></button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function CampoValor({ valor, aoMudar, grande = false, autoFocus = false, placeholder = "0,00", id }) {
  return (
    <div className={`fin-campo-valor ${grande ? "grande" : ""}`}>
      <span>R$</span>
      <input
        id={id}
        inputMode="decimal"
        value={valor}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => aoMudar(e.target.value.replace(/[^\d.,]/g, ""))}
      />
    </div>
  );
}

export function Aviso({ tipo = "info", children }) {
  return (
    <div className={`inline-alert ${tipo}`}>
      <Icon name={tipo === "error" || tipo === "warning" ? "alert" : "check"} size={15} />
      <span>{children}</span>
    </div>
  );
}

function Conferido({ rotulo, planilha, sistema, formato = "dinheiro" }) {
  const bate = planilha === null || planilha === undefined || Math.abs(Number(planilha) - Number(sistema)) < 0.01;
  const mostrar = (v) => (formato === "toneladas" ? toneladas(v) : brl(v));
  return (
    <li className={bate ? "bate" : "diverge"}>
      <span>{rotulo}</span>
      <span className="fin-conferido-valores">
        {planilha !== null && planilha !== undefined && <small>planilha {mostrar(planilha)}</small>}
        <strong>{mostrar(sistema)}</strong>
      </span>
      <Icon name={bate ? "check" : "alert"} size={15} />
    </li>
  );
}

// Envia a planilha, mostra a previa conferida com os totais dela e so grava
// quando a pessoa confirma.
export function ImportarPlanilha({ aoFechar, aoImportar }) {
  const [arquivo, setArquivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [feito, setFeito] = useState(null);
  const entrada = useRef(null);

  async function escolher(novo) {
    if (!novo) return;
    setArquivo(novo);
    setPrevia(null);
    setFeito(null);
    setErro("");
    setCarregando(true);
    try {
      setPrevia(await api.importarPlanilha(novo, false));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  async function aplicar() {
    setCarregando(true);
    setErro("");
    try {
      const resultado = await api.importarPlanilha(arquivo, true, previa?.competencia);
      setFeito(resultado);
      aoImportar?.(resultado);
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  const resumo = feito || previa;
  return (
    <Modal titulo="Importar planilha" subtitulo="Fluxo de Caixa ou Controle de Carregamentos (.xlsx)" aoFechar={aoFechar} largura={640}>
      <label
        className={`fin-soltar ${arquivo ? "com-arquivo" : ""}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); escolher(e.dataTransfer.files?.[0]); }}
      >
        <input ref={entrada} type="file" accept=".xlsx" onChange={(e) => escolher(e.target.files?.[0])} />
        <Icon name="upload" size={20} />
        <span>
          <strong>{arquivo ? arquivo.name : "Arraste a planilha aqui"}</strong>
          <small>{arquivo ? "Clique para trocar o arquivo" : "ou clique para escolher"}</small>
        </span>
      </label>

      {carregando && <Aviso>{feito || !previa ? "Lendo a planilha..." : "Importando..."}</Aviso>}
      {erro && <Aviso tipo="error">{erro}</Aviso>}

      {resumo && resumo.tipo === "fluxo_caixa" && (
        <div className="fin-previa">
          <p className="fin-previa-titulo">
            {feito ? "Importado." : "Fluxo de caixa de"} <strong>{diaBr(resumo.data)}</strong> · {resumo.lancamentos.novos} lançamentos novos
            {resumo.lancamentos.ja_existiam > 0 && `, ${resumo.lancamentos.ja_existiam} já estavam no sistema`}
            {resumo.transferencias_ligadas > 0 && ` · ${resumo.transferencias_ligadas} transferências entre contas reconhecidas`}
          </p>
          <ul className="fin-conferido">
            {resumo.contas.map((c) => (
              <Conferido key={c.nome} rotulo={`${c.nome}${c.criada ? " (conta nova)" : ""}`} planilha={c.saldo_final_planilha} sistema={c.saldo_final_sistema} />
            ))}
            <Conferido rotulo="Saldo em conta" planilha={resumo.conferencia.saldo_final_planilha} sistema={resumo.conferencia.saldo_final_sistema} />
          </ul>
          {resumo.contas.filter((c) => c.divergencia).map((c) => (
            <Aviso key={c.nome} tipo="warning">
              {c.nome}: a planilha abre o dia com {brl(c.divergencia.planilha)}, mas o sistema calcula {brl(c.divergencia.sistema)}. Confira lançamentos de dias anteriores.
            </Aviso>
          ))}
        </div>
      )}

      {resumo && resumo.tipo === "controle" && (
        <div className="fin-previa">
          <p className="fin-previa-titulo">
            {feito ? "Importado." : "Controle de"} <strong>{nomeCompetencia(resumo.competencia)}</strong> · {resumo.carregamentos.novos} carregamentos,{" "}
            {(resumo.despesas_empresa?.novas || 0) + (resumo.despesas_pessoal?.novas || 0)} despesas, {resumo.dividas?.novas || 0} dívidas
          </p>
          <ul className="fin-conferido">
            <Conferido rotulo="Toneladas" formato="toneladas" planilha={resumo.conferencia.toneladas.planilha} sistema={resumo.conferencia.toneladas.sistema} />
            <Conferido rotulo="Lucro bruto" planilha={resumo.conferencia.lucro_bruto.planilha} sistema={resumo.conferencia.lucro_bruto.sistema} />
            <Conferido rotulo="Despesas da empresa" planilha={resumo.conferencia.despesas_empresa.planilha} sistema={resumo.conferencia.despesas_empresa.sistema} />
            <Conferido rotulo="Gastos pessoais" planilha={resumo.conferencia.gastos_pessoais.planilha} sistema={resumo.conferencia.gastos_pessoais.sistema} />
            <Conferido rotulo="Custo fixo da precificação" planilha={resumo.conferencia.custo_fixo_precificacao.planilha} sistema={resumo.conferencia.custo_fixo_precificacao.sistema} />
          </ul>
          {(resumo.avisos || []).map((aviso) => <Aviso key={aviso} tipo="warning">{aviso}</Aviso>)}
        </div>
      )}

      <footer className="fin-modal-rodape">
        <button type="button" className="btn-secondary" onClick={aoFechar}>{feito ? "Fechar" : "Cancelar"}</button>
        {!feito && (
          <button type="button" className="btn-primary" disabled={!previa || carregando} onClick={aplicar}>
            Importar para o sistema
          </button>
        )}
      </footer>
    </Modal>
  );
}
