// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { useEffect, useState } from "react";
import {
  ApiError,
  Compromisso,
  Historico,
  Slot,
  api,
  hojeISO,
  horaLocal,
} from "../api";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-03: ficha completa + histórico (quem, quando, por quê) e as ações.
// Cancelar segue o padrão propor → confirmar da própria API: a primeira
// chamada devolve a prévia + confirmation_token; o humano aprova e a
// segunda executa — a UI não tem caminho privilegiado.

const ACAO_LEGIVEL: Record<string, string> = {
  criado: "Criado",
  reagendado: "Reagendado",
  cancelado: "Cancelado",
  confirmado: "Confirmado pelo cliente",
  no_show: "Falta registrada",
};

interface Props {
  compromisso: Compromisso;
  nomeServico: string;
  onFechar: () => void;
  onMudou: () => void;
}

export function Detalhe({ compromisso: c, nomeServico, onFechar, onMudou }: Props) {
  const [historico, setHistorico] = useState<Historico[]>([]);
  const [modo, setModo] = useState<"ver" | "reagendar" | "cancelar" | "falta" | "serie">("ver");
  const [erro, setErro] = useState<unknown>(null);
  const [ocupado, setOcupado] = useState(false);

  const [novaData, setNovaData] = useState(hojeISO());
  const [slots, setSlots] = useState<Slot[]>([]);

  const [motivo, setMotivo] = useState("");
  const [tokenConfirmacao, setTokenConfirmacao] = useState<string | null>(null);
  const avisar = usarToast();

  useEffect(() => {
    api.get<Historico[]>(`/appointments/${c.id}/history`).then(setHistorico).catch(() => {});
  }, [c.id]);

  // Esc fecha o painel (DS §3.7)
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") onFechar();
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onFechar]);

  useEffect(() => {
    if (modo !== "reagendar") return;
    api
      .get<Slot[]>(
        `/slots?service_id=${c.service_id}&resource_id=${c.resource_id}` +
          `&from=${novaData}T00:00:00-03:00&to=${novaData}T23:59:00-03:00&limit=50`,
      )
      .then(setSlots)
      .catch(setErro);
  }, [modo, novaData, c.service_id, c.resource_id]);

  async function executar(acao: () => Promise<unknown>, feito: string) {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
      avisar(feito);
      onMudou();
    } catch (e) {
      // padrão propor → confirmar: o 409 traz a prévia e o token
      if (e instanceof ApiError && e.erro.code === "CONFIRMACAO_NECESSARIA") {
        setTokenConfirmacao(e.erro.confirmation_token ?? null);
      } else {
        setErro(e);
      }
    } finally {
      setOcupado(false);
    }
  }

  const encerrado = ["cancelado", "realizado", "no_show"].includes(c.status);

  return (
    <div className="painel-fundo" onClick={onFechar}>
      <aside className="painel" onClick={(e) => e.stopPropagation()}>
        <button className="fechar" onClick={onFechar} aria-label="Fechar painel">
          ×
        </button>
        <h2>{c.cliente_nome}</h2>
        <div className="horario-grande">{c.label_humano}</div>
        <span className={`selo ${c.status}`}>{c.status.replace("_", "-")}</span>{" "}
        {c.series_id && <span className="selo serie">recorrente</span>}{" "}
        {c.risco_no_show === "alto" && <span className="selo risco">risco de falta alto</span>}
        {c.risco_detalhe && c.risco_no_show !== "baixo" && (
          <details className="risco-composicao">
            <summary>Por que o risco é {c.risco_no_show}?</summary>
            <ul>
              {c.risco_detalhe.fatores.map((f) => (
                <li key={f.fator}>
                  {f.detalhe} <span className="mono">+{f.pontos}</span>
                </li>
              ))}
            </ul>
            <p>
              {c.risco_detalhe.pontos} ponto(s) somados por fatores observáveis — sem modelo
              estatístico. O risco alto só pede uma confirmação a mais; nunca cancela nada.
            </p>
          </details>
        )}
        <dl>
          <dt>Serviço</dt>
          <dd>{nomeServico}</dd>
          <dt>Telefone</dt>
          <dd className="mono">{c.cliente_telefone}</dd>
          <dt>Origem</dt>
          <dd>{c.origem}</dd>
          {c.observacoes && (
            <>
              <dt>Observações</dt>
              <dd>{c.observacoes}</dd>
            </>
          )}
        </dl>

        <ErroAviso erro={erro} />

        {modo === "ver" && !encerrado && (
          <div className="acoes">
            {c.status === "agendado" && (
              <button
                className="acao primario"
                disabled={ocupado}
                onClick={() =>
                  executar(() => api.post(`/appointments/${c.id}/confirm`), "Presença confirmada")
                }
              >
                Confirmar presença
              </button>
            )}
            <button className="acao" onClick={() => setModo("reagendar")}>
              Reagendar
            </button>
            <button className="acao perigo" onClick={() => setModo("cancelar")}>
              Cancelar horário
            </button>
            <button className="acao perigo" onClick={() => setModo("falta")}>
              Marcar falta
            </button>
            {c.series_id && (
              <button className="acao perigo" onClick={() => setModo("serie")}>
                Cancelar futuras da série
              </button>
            )}
          </div>
        )}

        {modo === "serie" && (
          <div>
            <label className="campo">
              Motivo do cancelamento da série
              <input
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="ex.: cliente encerrou o pacote"
              />
            </label>
            <div className="acoes">
              <p style={{ width: "100%", fontSize: 14 }}>
                Cancela <strong>todas as ocorrências futuras</strong> desta série — as passadas
                não mudam. Os horários voltam para a grade na hora.
              </p>
              {tokenConfirmacao ? (
                <button
                  className="acao perigo"
                  disabled={ocupado}
                  onClick={() =>
                    executar(
                      () =>
                        api.post(`/appointments/recorrentes/${c.series_id}/cancel`, {
                          motivo,
                          confirmation_token: tokenConfirmacao,
                        }),
                      "Série cancelada — horários de volta na grade",
                    )
                  }
                >
                  Confirmar cancelamento da série
                </button>
              ) : (
                <button
                  className="acao perigo"
                  disabled={ocupado || !motivo.trim()}
                  onClick={() =>
                    executar(
                      () =>
                        api.post(`/appointments/recorrentes/${c.series_id}/cancel`, { motivo }),
                      "Série cancelada — horários de volta na grade",
                    )
                  }
                >
                  Cancelar futuras da série
                </button>
              )}
              <button
                className="acao"
                onClick={() => {
                  setTokenConfirmacao(null);
                  setModo("ver");
                }}
              >
                Voltar
              </button>
            </div>
          </div>
        )}

        {modo === "reagendar" && (
          <div>
            <label className="campo">
              Novo dia
              <input type="date" value={novaData} onChange={(e) => setNovaData(e.target.value)} />
            </label>
            {slots.length === 0 ? (
              <p className="vazio">Sem horários livres neste dia — tente outro.</p>
            ) : (
              <div className="slots-livres">
                {slots.map((s) => {
                  const { h, m } = horaLocal(s.inicio);
                  return (
                    <button
                      key={s.inicio}
                      disabled={ocupado}
                      title={s.label_humano}
                      onClick={() =>
                        executar(
                          () =>
                            api.post(`/appointments/${c.id}/reschedule`, {
                              novo_inicio: s.inicio,
                            }),
                          `Reagendado para ${s.label_humano}`,
                        )
                      }
                    >
                      {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")}
                    </button>
                  );
                })}
              </div>
            )}
            <button className="acao" onClick={() => setModo("ver")}>
              Voltar
            </button>
          </div>
        )}

        {modo === "cancelar" && (
          <div>
            <label className="campo">
              Motivo do cancelamento
              <input
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="ex.: cliente pediu"
              />
            </label>
            {tokenConfirmacao ? (
              <div className="acoes">
                <p style={{ width: "100%", fontSize: 14 }}>
                  Cancelar <strong>{c.cliente_nome}</strong>, {c.label_humano}? O horário volta
                  para a grade na hora.
                </p>
                <button
                  className="acao perigo"
                  disabled={ocupado}
                  onClick={() =>
                    executar(
                      () =>
                        api.post(`/appointments/${c.id}/cancel`, {
                          motivo,
                          confirmation_token: tokenConfirmacao,
                        }),
                      "Horário cancelado — o slot voltou para a grade",
                    )
                  }
                >
                  Confirmar cancelamento
                </button>
                <button className="acao" onClick={() => setTokenConfirmacao(null)}>
                  Voltar
                </button>
              </div>
            ) : (
              <div className="acoes">
                <button
                  className="acao perigo"
                  disabled={ocupado || !motivo.trim()}
                  onClick={() =>
                    executar(
                      () => api.post(`/appointments/${c.id}/cancel`, { motivo }),
                      "Horário cancelado — o slot voltou para a grade",
                    )
                  }
                >
                  Cancelar horário
                </button>
                <button className="acao" onClick={() => setModo("ver")}>
                  Voltar
                </button>
              </div>
            )}
          </div>
        )}

        {modo === "falta" && (
          <div className="acoes">
            <p style={{ width: "100%", fontSize: 14 }}>
              Registrar falta de <strong>{c.cliente_nome}</strong>? Isso alimenta o histórico de
              risco do cliente.
            </p>
            <button
              className="acao perigo"
              disabled={ocupado}
              onClick={() =>
                executar(() => api.post(`/appointments/${c.id}/no-show`), "Falta registrada")
              }
            >
              Registrar falta
            </button>
            <button className="acao" onClick={() => setModo("ver")}>
              Voltar
            </button>
          </div>
        )}

        <div className="historico">
          <h3>Histórico</h3>
          <ul>
            {historico.map((h, i) => (
              <li key={i}>
                <strong>{ACAO_LEGIVEL[h.acao] ?? h.acao}</strong>
                {h.origem && <> · por {h.origem}</>}
                {h.motivo && <> · “{h.motivo}”</>}
                <span className="mono" style={{ float: "right" }}>
                  {new Date(h.em).toLocaleString("pt-BR", {
                    timeZone: "America/Sao_Paulo",
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
