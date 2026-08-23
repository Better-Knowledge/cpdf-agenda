// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { FormEvent, useCallback, useEffect, useState } from "react";
import { FilaEntrada, Servico, api, hojeISO } from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-06: a fila de espera. O que a tela precisa deixar claro o tempo todo:
// uma oferta em aberto NÃO segura o horário — ele continua na grade e quem
// confirmar primeiro leva. Esconder isso geraria promessa que o produto não
// cumpre.

const STATUS_LEGIVEL: Record<string, string> = {
  aguardando: "aguardando",
  ofertado: "oferta enviada",
  aceito: "aceitou",
  expirado: "não respondeu",
  cancelado: "saiu da fila",
};

function minutosRestantes(expiraEm: string): number {
  return Math.max(0, Math.round((new Date(expiraEm).getTime() - Date.now()) / 60000));
}

const FORM_VAZIO = {
  servico: "",
  nome: "",
  telefone: "",
  dia: hojeISO(),
  horaInicio: "09:00",
  horaFim: "18:00",
};

export function Fila() {
  const [entradas, setEntradas] = useState<FilaEntrada[]>([]);
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [mostrarEncerrados, setMostrarEncerrados] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const [ocupado, setOcupado] = useState(false);
  const [form, setForm] = useState(FORM_VAZIO);
  const avisar = usarToast();

  const carregar = useCallback(async () => {
    const rota = mostrarEncerrados ? "/waitlist?incluir_encerrados=true" : "/waitlist";
    setEntradas(await api.get<FilaEntrada[]>(rota));
  }, [mostrarEncerrados]);

  useEffect(() => {
    carregar().catch(setErro);
    api
      .get<{ items: Servico[] }>("/services?limit=50")
      .then((r) => {
        setServicos(r.items);
        setForm((f) => (f.servico ? f : { ...f, servico: r.items[0]?.id ?? "" }));
      })
      .catch(setErro);
  }, [carregar]);

  // Enquanto houver oferta em aberto, o relógio corre: recarrega de minuto em
  // minuto para o prestador ver a janela encolher.
  useEffect(() => {
    if (!entradas.some((e) => e.status === "ofertado")) return;
    const timer = setInterval(() => carregar().catch(() => {}), 60000);
    return () => clearInterval(timer);
  }, [entradas, carregar]);

  async function agir(acao: () => Promise<unknown>, feito: string) {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
      avisar(feito);
      await carregar();
      return true;
    } catch (e) {
      setErro(e);
      return false;
    } finally {
      setOcupado(false);
    }
  }

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    const ok = await agir(
      () =>
        api.post("/waitlist", {
          service_id: form.servico,
          cliente_nome: form.nome,
          cliente_telefone: form.telefone,
          janela_inicio: `${form.dia}T${form.horaInicio}:00-03:00`,
          janela_fim: `${form.dia}T${form.horaFim}:00-03:00`,
        }),
      "Entrou na fila",
    );
    if (ok) setForm({ ...FORM_VAZIO, servico: form.servico, dia: form.dia });
  }

  const nomeServico = (id: string) => servicos.find((s) => s.id === id)?.nome ?? "serviço";
  const esperando = entradas.filter((e) => e.status === "aguardando" || e.status === "ofertado");

  return (
    <>
      <h1>
        Fila de <em>espera</em>
      </h1>
      <p className="subtitulo">
        Quem ficou sem horário e quer ser avisado quando vagar. Ao cancelar um compromisso, o
        primeiro da fila recebe a oferta pelo canal automaticamente.
      </p>
      <ErroAviso erro={erro} />

      <div className="cartao" style={{ marginBottom: 20 }}>
        {entradas.length === 0 ? (
          <div className="vazio">Ninguém esperando — a agenda está dando conta.</div>
        ) : (
          <table className="lista">
            <thead>
              <tr>
                <th>#</th>
                <th>Cliente</th>
                <th>Serviço</th>
                <th>Quando gostaria</th>
                <th>Situação</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {entradas.map((e) => {
                const encerrada = !["aguardando", "ofertado"].includes(e.status);
                return (
                  <tr key={e.id} style={encerrada ? { color: "var(--fg-soft)" } : undefined}>
                    <td className="mono">{e.posicao ?? "—"}</td>
                    <td>
                      <strong>{e.cliente_nome}</strong>
                      <br />
                      <span className="mono" style={{ fontSize: 12, color: "var(--fg-muted)" }}>
                        {e.cliente_telefone}
                      </span>
                    </td>
                    <td>{nomeServico(e.service_id)}</td>
                    <td style={{ fontSize: 14 }}>{e.janela_humana}</td>
                    <td>
                      <span className={`selo fila-${e.status}`}>{STATUS_LEGIVEL[e.status]}</span>
                      {e.status === "ofertado" && e.expira_em && (
                        <div style={{ fontSize: 12, color: "var(--fg-muted)", marginTop: 4 }}>
                          responde em {minutosRestantes(e.expira_em)} min
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {!encerrada && (
                        <BotaoConfirmar
                          miudo
                          rotulo="Remover"
                          confirmacao="Tirar da fila?"
                          desabilitado={ocupado}
                          onConfirmar={() =>
                            agir(() => api.delete(`/waitlist/${e.id}`), "Saiu da fila")
                          }
                        />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {esperando.some((e) => e.status === "ofertado") && (
          <p className="nota-driver">
            Há oferta em aberto. O horário <strong>continua livre na grade</strong> enquanto
            isso — não está reservado. Quem confirmar primeiro leva, e a mensagem enviada diz
            exatamente isso.
          </p>
        )}

        {entradas.some((e) => e.avisos.length > 0) &&
          entradas
            .filter((e) => e.avisos.length > 0)
            .map((e) => (
              <p key={e.id} className="aviso-erro" style={{ fontSize: 13 }}>
                <strong>{e.cliente_nome}:</strong> {e.avisos.join(" ")}
              </p>
            ))}

        <label style={{ display: "block", marginTop: 10, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={mostrarEncerrados}
            onChange={(evento) => setMostrarEncerrados(evento.target.checked)}
          />{" "}
          Mostrar quem já saiu da fila
        </label>
      </div>

      <form className="cartao" onSubmit={entrar}>
        <h2 className="bloco">Colocar alguém na fila</h2>
        <div className="formulario-linha">
          <label className="campo">
            Serviço
            <select
              value={form.servico}
              onChange={(e) => setForm({ ...form, servico: e.target.value })}
              required
            >
              {servicos.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </select>
          </label>
          <label className="campo">
            Nome
            <input
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
              required
            />
          </label>
          <label className="campo">
            Contato
            <input
              value={form.telefone}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
              placeholder="+5511900000000 ou tg:123456789"
              required
            />
          </label>
        </div>
        <div className="formulario-linha">
          <label className="campo">
            Dia desejado
            <input
              type="date"
              value={form.dia}
              onChange={(e) => setForm({ ...form, dia: e.target.value })}
            />
          </label>
          <label className="campo">
            A partir de
            <input
              type="time"
              value={form.horaInicio}
              onChange={(e) => setForm({ ...form, horaInicio: e.target.value })}
            />
          </label>
          <label className="campo">
            Até
            <input
              type="time"
              value={form.horaFim}
              onChange={(e) => setForm({ ...form, horaFim: e.target.value })}
            />
          </label>
        </div>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 10 }}>
          A fila é por <em>janela</em>, não por horário exato — se o horário que a pessoa quer
          está livre, agende direto.
        </p>
        <button className="acao primario" disabled={ocupado || !form.nome.trim()}>
          {ocupado ? "Salvando…" : "Colocar na fila"}
        </button>
      </form>
    </>
  );
}
