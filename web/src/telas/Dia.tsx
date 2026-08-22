import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Compromisso,
  Recurso,
  Servico,
  api,
  dataPorExtenso,
  hojeISO,
  horaLocal,
  mudarDia,
} from "../api";
import { ErroAviso } from "../ErroAviso";
import { Detalhe } from "./Detalhe";

// A folha do dia: régua de horas na margem, uma coluna por recurso,
// compromissos como marcações na pauta. Espelha T-02 do PRD §12.
const HORA_INICIO = 7;
const HORA_FIM = 20;
const ALTURA_HORA = 56;

function topo(iso: string): number {
  const { h, m } = horaLocal(iso);
  return (h - HORA_INICIO) * ALTURA_HORA + (m / 60) * ALTURA_HORA;
}

export function Dia() {
  const [data, setData] = useState(hojeISO());
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [compromissos, setCompromissos] = useState<Compromisso[]>([]);
  const [selecionado, setSelecionado] = useState<Compromisso | null>(null);
  const [agora, setAgora] = useState(new Date());
  const [erro, setErro] = useState<unknown>(null);

  const carregar = useCallback(async () => {
    try {
      setCompromissos(await api.get<Compromisso[]>(`/appointments?date=${data}`));
      setAgora(new Date());
      setErro(null);
    } catch (e) {
      setErro(e);
    }
  }, [data]);

  useEffect(() => {
    api.get<{ items: Recurso[] }>("/resources").then((r) => setRecursos(r.items));
    api.get<{ items: Servico[] }>("/services?limit=50").then((r) => setServicos(r.items));
  }, []);

  // T-02 reflete mudanças feitas por conversa sem refresh manual (polling basta)
  useEffect(() => {
    carregar();
    const intervalo = setInterval(carregar, 10_000);
    return () => clearInterval(intervalo);
  }, [carregar]);

  const nomeServico = useMemo(
    () => new Map(servicos.map((s) => [s.id, s.nome])),
    [servicos],
  );
  const horas = Array.from({ length: HORA_FIM - HORA_INICIO + 1 }, (_, i) => HORA_INICIO + i);
  const alturaTotal = (HORA_FIM - HORA_INICIO) * ALTURA_HORA;
  const ehHoje = data === hojeISO();
  const topoAgora = topo(agora.toISOString());

  return (
    <>
      <h1>Agenda do dia</h1>
      <p className="subtitulo">
        O que a conversa marcou, confirmou e cancelou — atualizado sozinho a cada 10 s.
      </p>
      <div className="dia-cabecalho">
        <button className="navega" onClick={() => setData(mudarDia(data, -1))} aria-label="Dia anterior">
          ‹
        </button>
        <button className="navega" onClick={() => setData(hojeISO())}>
          Hoje
        </button>
        <button className="navega" onClick={() => setData(mudarDia(data, 1))} aria-label="Próximo dia">
          ›
        </button>
        <strong>{dataPorExtenso(data)}</strong>
      </div>
      <ErroAviso erro={erro} />

      {recursos.length === 0 ? (
        <div className="cartao vazio">
          Nenhum recurso cadastrado ainda — comece criando um em “Grade e bloqueios”.
        </div>
      ) : (
        <div className="quadro-dia" style={{ "--colunas": recursos.length } as React.CSSProperties}>
          <div />
          {recursos.map((r) => (
            <div key={r.id} className="titulo-coluna">
              {r.nome}
            </div>
          ))}

          <div className="regua" style={{ height: alturaTotal }}>
            {horas.map((h) => (
              <span key={h} className="hora" style={{ top: (h - HORA_INICIO) * ALTURA_HORA }}>
                {String(h).padStart(2, "0")}h
              </span>
            ))}
          </div>

          {recursos.map((r) => (
            <div key={r.id} className="coluna-recurso" style={{ height: alturaTotal }}>
              {horas.map((h) => (
                <div
                  key={h}
                  className="linha-pauta"
                  style={{ top: (h - HORA_INICIO) * ALTURA_HORA }}
                />
              ))}
              {ehHoje && topoAgora > 0 && topoAgora < alturaTotal && (
                <div className="linha-agora" style={{ top: topoAgora }} />
              )}
              {compromissos
                .filter((c) => c.resource_id === r.id)
                .map((c) => {
                  const inicio = horaLocal(c.inicio);
                  const fim = horaLocal(c.fim);
                  return (
                    <button
                      key={c.id}
                      className={`compromisso ${c.status}`}
                      style={{
                        top: topo(c.inicio),
                        height: Math.max(36, topo(c.fim) - topo(c.inicio) - 3),
                      }}
                      onClick={() => setSelecionado(c)}
                    >
                      <span className="quem">{c.cliente_nome}</span>{" "}
                      {c.risco_no_show === "alto" && <span className="selo risco">risco de falta</span>}
                      <div className="quando">
                        {String(inicio.h).padStart(2, "0")}:{String(inicio.m).padStart(2, "0")}–
                        {String(fim.h).padStart(2, "0")}:{String(fim.m).padStart(2, "0")} ·{" "}
                        {nomeServico.get(c.service_id) ?? "serviço"}
                      </div>
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
      )}

      {selecionado && (
        <Detalhe
          compromisso={selecionado}
          nomeServico={nomeServico.get(selecionado.service_id) ?? "Serviço"}
          onFechar={() => setSelecionado(null)}
          onMudou={() => {
            setSelecionado(null);
            carregar();
          }}
        />
      )}
    </>
  );
}
