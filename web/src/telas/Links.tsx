// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { FormEvent, useEffect, useState } from "react";
import { LinkPublico, Servico, api } from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-07: links públicos de auto-agendamento (RF-13).
//
// A tela precisa dizer o tempo todo qual é o lugar deste recurso no produto:
// a conversa é a via principal, o link é a alternativa para quem prefere
// clicar. E a caução, nesta fase, apenas **informa** o valor na página — a
// cobrança via Pix é roadmap, e prometer o contrário na UI seria mentira.

export function Links() {
  const [links, setLinks] = useState<LinkPublico[]>([]);
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [ocupado, setOcupado] = useState(false);
  const [form, setForm] = useState({ servico: "", slug: "", caucao: "" });
  const avisar = usarToast();

  async function carregar() {
    setLinks(await api.get<LinkPublico[]>("/booking-links"));
  }

  useEffect(() => {
    carregar().catch(setErro);
    api
      .get<{ items: Servico[] }>("/services?limit=50")
      .then((r) => {
        setServicos(r.items);
        setForm((f) => (f.servico ? f : { ...f, servico: r.items[0]?.id ?? "" }));
      })
      .catch(setErro);
  }, []);

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

  async function criar(evento: FormEvent) {
    evento.preventDefault();
    const caucao = form.caucao.trim();
    const ok = await agir(
      () =>
        api.post("/booking-links", {
          service_id: form.servico,
          slug: form.slug.trim() || undefined,
          exige_caucao: Boolean(caucao),
          valor_caucao: caucao || undefined,
        }),
      "Link criado",
    );
    if (ok) setForm({ ...form, slug: "", caucao: "" });
  }

  const nomeServico = (id: string) => servicos.find((s) => s.id === id)?.nome ?? "serviço";

  return (
    <>
      <h1>
        Links <em>públicos</em>
      </h1>
      <p className="subtitulo">
        Uma página onde o cliente escolhe o horário sozinho. Ela usa o mesmo motor de
        disponibilidade da conversa — mesmos buffers, mesmos bloqueios, mesma garantia de que
        ninguém marca em cima de ninguém.
      </p>
      <ErroAviso erro={erro} />

      <div className="cartao" style={{ marginBottom: 20 }}>
        {links.length === 0 ? (
          <div className="vazio">
            Nenhum link ainda. A conversa segue funcionando sem ele — o link é a via opcional.
          </div>
        ) : (
          <table className="lista">
            <thead>
              <tr>
                <th>Endereço</th>
                <th>Serviço</th>
                <th>Sinal</th>
                <th>Situação</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {links.map((l) => (
                <tr key={l.id} style={l.ativo ? undefined : { color: "var(--fg-soft)" }}>
                  <td>
                    <a href={l.url} target="_blank" rel="noreferrer" className="mono">
                      /agendar/{l.slug}
                    </a>
                    <br />
                    <button
                      type="button"
                      className="acao miuda"
                      onClick={() => {
                        navigator.clipboard?.writeText(l.url);
                        avisar("Endereço copiado");
                      }}
                    >
                      Copiar endereço
                    </button>
                  </td>
                  <td>{nomeServico(l.service_id)}</td>
                  <td>
                    {l.exige_caucao && l.valor_caucao ? (
                      <span className="valor">R$ {l.valor_caucao}</span>
                    ) : (
                      <span style={{ color: "var(--fg-muted)" }}>—</span>
                    )}
                  </td>
                  <td>
                    <span className={`selo ${l.ativo ? "confirmado" : "cancelado"}`}>
                      {l.ativo ? "ativo" : "desativado"}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {l.ativo ? (
                      <BotaoConfirmar
                        miudo
                        rotulo="Desativar"
                        confirmacao="Desativar o link?"
                        desabilitado={ocupado}
                        onConfirmar={() =>
                          agir(() => api.delete(`/booking-links/${l.id}`), "Link desativado")
                        }
                      />
                    ) : (
                      <button
                        type="button"
                        className="acao miuda"
                        disabled={ocupado}
                        onClick={() =>
                          agir(
                            () => api.patch(`/booking-links/${l.id}`, { ativo: true }),
                            "Link reativado",
                          )
                        }
                      >
                        Reativar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {links.some((l) => !l.ativo) && (
          <p className="nota-driver">
            Link desativado não some: quem abrir o endereço vê uma mensagem explicando que o
            agendamento por ali está fechado, com o convite para falar pelo WhatsApp.
          </p>
        )}
      </div>

      <form className="cartao" onSubmit={criar}>
        <h2 className="bloco">Criar um link</h2>
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
            Endereço (opcional)
            <input
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              placeholder="corte-masculino"
            />
          </label>
          <label className="campo">
            Sinal em R$ (opcional)
            <input
              value={form.caucao}
              onChange={(e) => setForm({ ...form, caucao: e.target.value })}
              placeholder="30.00"
              inputMode="decimal"
            />
          </label>
        </div>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 10 }}>
          O sinal é <strong>informativo</strong> nesta versão: a página mostra o valor e você
          combina o pagamento com o cliente. Cobrança automática por Pix é passo seguinte.
        </p>
        <button className="acao primario" disabled={ocupado || !form.servico}>
          {ocupado ? "Criando…" : "Criar link"}
        </button>
      </form>
    </>
  );
}
