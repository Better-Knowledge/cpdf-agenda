// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { FormEvent, useEffect, useState } from "react";
import {
  ConexaoGoogle,
  ConfigCalendly,
  FeedIcs,
  FeedIcsCriado,
  Recurso,
  Servico,
  api,
} from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-08: as três formas de o compromisso aparecer fora daqui.
//
// A tela é organizada pela pergunta que o prestador realmente faz — "por que
// meu Google não atualizou?" — e por isso diz, em cada bloco, qual é a
// garantia de tempo: o push é minutos, o feed .ics é horas (o Google relê
// quando quer), e o Calendly é one-way.

export function Calendarios() {
  const [conexoes, setConexoes] = useState<ConexaoGoogle[]>([]);
  const [feeds, setFeeds] = useState<FeedIcs[]>([]);
  const [calendly, setCalendly] = useState<ConfigCalendly | null>(null);
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [revelado, setRevelado] = useState<{ id: string; url: string } | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const [ocupado, setOcupado] = useState(false);
  const [feedForm, setFeedForm] = useState({ recurso: "", modo: "completo" });
  const [calendlyForm, setCalendlyForm] = useState({
    servico: "",
    recurso: "",
    chave: "",
    lembretes: false,
  });
  const avisar = usarToast();

  async function carregar() {
    const [c, f, cal] = await Promise.all([
      api.get<ConexaoGoogle[]>("/integracoes/google"),
      api.get<FeedIcs[]>("/ics/tokens"),
      api.get<ConfigCalendly | null>("/integracoes/calendly"),
    ]);
    setConexoes(c);
    setFeeds(f.filter((x) => !x.revogado_em));
    setCalendly(cal);
  }

  useEffect(() => {
    carregar().catch(setErro);
    api
      .get<{ items: Recurso[] }>("/resources?limit=50")
      .then((r) => {
        setRecursos(r.items);
        setCalendlyForm((f) => (f.recurso ? f : { ...f, recurso: r.items[0]?.id ?? "" }));
      })
      .catch(setErro);
    api
      .get<{ items: Servico[] }>("/services?limit=50")
      .then((r) => {
        setServicos(r.items);
        setCalendlyForm((f) => (f.servico ? f : { ...f, servico: r.items[0]?.id ?? "" }));
      })
      .catch(setErro);

    // O callback do OAuth devolve o navegador para cá com o resultado na URL.
    const resultado = new URLSearchParams(window.location.search).get("google");
    if (resultado === "conectado") avisar("Google Calendar conectado");
    if (resultado === "cancelado") avisar("Conexão cancelada na tela do Google", "erro");
    if (resultado === "sem_refresh")
      avisar("O Google não devolveu autorização duradoura — tente de novo", "erro");
    if (resultado) window.history.replaceState({}, "", window.location.pathname);
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

  async function conectarGoogle(resourceId: string) {
    setErro(null);
    try {
      const { url } = await api.post<{ url: string }>("/integracoes/google/conectar", {
        resource_id: resourceId,
      });
      window.location.href = url; // a autorização acontece no Google, não aqui
    } catch (e) {
      setErro(e);
    }
  }

  async function criarFeed(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      const criado = await api.post<FeedIcsCriado>("/ics/tokens", {
        resource_id: feedForm.recurso || undefined,
        modo: feedForm.modo,
      });
      setRevelado({ id: criado.id, url: criado.url_completa });
      avisar("Feed criado");
      await carregar();
    } catch (e) {
      setErro(e);
    } finally {
      setOcupado(false);
    }
  }

  async function revelarFeed(id: string) {
    setErro(null);
    try {
      const dados = await api.post<FeedIcsCriado>(`/ics/tokens/${id}/revelar`);
      setRevelado({ id, url: dados.url_completa });
    } catch (e) {
      setErro(e);
    }
  }

  async function salvarCalendly(evento: FormEvent) {
    evento.preventDefault();
    const ok = await agir(
      () =>
        api.put("/integracoes/calendly", {
          service_id: calendlyForm.servico,
          resource_id: calendlyForm.recurso,
          chave_assinatura: calendlyForm.chave,
          cria_lembretes: calendlyForm.lembretes,
        }),
      "Calendly configurado",
    );
    if (ok) setCalendlyForm({ ...calendlyForm, chave: "" });
  }

  const nomeRecurso = (id: string | null) =>
    id ? (recursos.find((r) => r.id === id)?.nome ?? "recurso") : "todos os recursos";
  const conectado = (id: string) => conexoes.find((c) => c.resource_id === id && c.ativo);
  const precisaReconectar = (id: string) =>
    conexoes.find((c) => c.resource_id === id && c.precisa_reconectar);

  return (
    <>
      <h1>
        Calendários e <em>importações</em>
      </h1>
      <p className="subtitulo">
        Onde os compromissos desta agenda aparecem fora daqui — e de onde eles podem vir. Cada
        integração é opcional: sem nenhuma, o produto funciona igual.
      </p>
      <ErroAviso erro={erro} />

      {/* ── Google Calendar (RF-12) ────────────────────────────────────── */}
      <div className="cartao" style={{ marginBottom: 20 }}>
        <h2 className="bloco">Google Calendar</h2>
        <p style={{ fontSize: 14, color: "var(--fg-muted)", marginBottom: 14 }}>
          Conecte a conta de cada profissional. O compromisso aparece no Google em menos de um
          minuto, e reunião marcada direto lá <strong>bloqueia o horário aqui</strong> — a agenda
          para de oferecer o que já está tomado.
        </p>
        <table className="lista">
          <thead>
            <tr>
              <th>Recurso</th>
              <th>Situação</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {recursos.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.nome}</strong>
                </td>
                <td>
                  {conectado(r.id) ? (
                    <span className="selo confirmado">conectado</span>
                  ) : precisaReconectar(r.id) ? (
                    <span className="selo no_show">reconecte</span>
                  ) : (
                    <span className="selo desconhecido">não conectado</span>
                  )}
                </td>
                <td style={{ textAlign: "right" }}>
                  {conectado(r.id) ? (
                    <BotaoConfirmar
                      miudo
                      rotulo="Desconectar"
                      confirmacao="Desconectar o Google?"
                      desabilitado={ocupado}
                      onConfirmar={() =>
                        agir(
                          () => api.delete(`/integracoes/google/${r.id}`),
                          "Google desconectado",
                        )
                      }
                    />
                  ) : (
                    <button
                      type="button"
                      className="acao miuda"
                      disabled={ocupado}
                      onClick={() => conectarGoogle(r.id)}
                    >
                      Conectar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {conexoes.some((c) => c.precisa_reconectar) && (
          <p className="aviso-erro" style={{ fontSize: 13 }}>
            O Google passou a recusar a autorização de um dos recursos (revogada por lá, ou
            permissão retirada). Enquanto isso, os compromissos deixam de ir para o calendário e a
            agenda calcula só com os dados dela. Reconecte para voltar ao normal.
          </p>
        )}
        {conexoes.some((c) => c.ativo) && (
          <p className="nota-driver">
            A sincronização é de mão única: editar ou apagar o evento <em>no Google</em> não volta
            para cá. O evento criado leva esse aviso na descrição.
          </p>
        )}
      </div>

      {/* ── Feed .ics (RF-11) ──────────────────────────────────────────── */}
      <div className="cartao" style={{ marginBottom: 20 }}>
        <h2 className="bloco">Feed de calendário (.ics)</h2>
        <p style={{ fontSize: 14, color: "var(--fg-muted)", marginBottom: 14 }}>
          A opção sem login no Google: um endereço que você assina no Google Calendar, Apple
          Calendar ou Outlook. <strong>Atualiza em ciclos de horas</strong> — o app de calendário
          decide quando reler, e isso não está no nosso controle. Para ver na hora, use o Google
          Calendar acima.
        </p>
        {feeds.length > 0 && (
          <table className="lista">
            <thead>
              <tr>
                <th>Recurso</th>
                <th>Modo</th>
                <th>Endereço</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {feeds.map((f) => (
                <tr key={f.id}>
                  <td>{nomeRecurso(f.resource_id)}</td>
                  <td>
                    <span className="selo desconhecido">
                      {f.modo === "privado" ? "só ocupado" : "com nome do cliente"}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {revelado?.id === f.id ? revelado.url : f.url}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {revelado?.id === f.id ? (
                      <button
                        type="button"
                        className="acao miuda"
                        onClick={() => {
                          navigator.clipboard?.writeText(revelado.url);
                          avisar("Endereço copiado");
                        }}
                      >
                        Copiar
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="acao miuda"
                        onClick={() => revelarFeed(f.id)}
                      >
                        Mostrar endereço
                      </button>
                    )}{" "}
                    <BotaoConfirmar
                      miudo
                      rotulo="Revogar"
                      confirmacao="Revogar este feed?"
                      desabilitado={ocupado}
                      onConfirmar={() =>
                        agir(() => api.post(`/ics/tokens/${f.id}/revogar`), "Feed revogado")
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form className="formulario-linha" onSubmit={criarFeed} style={{ marginTop: 14 }}>
          <label className="campo">
            Recurso
            <select
              value={feedForm.recurso}
              onChange={(e) => setFeedForm({ ...feedForm, recurso: e.target.value })}
            >
              <option value="">Todos</option>
              {recursos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nome}
                </option>
              ))}
            </select>
          </label>
          <label className="campo">
            O que aparece
            <select
              value={feedForm.modo}
              onChange={(e) => setFeedForm({ ...feedForm, modo: e.target.value })}
            >
              <option value="completo">Serviço e nome do cliente</option>
              <option value="privado">Só "Ocupado"</option>
            </select>
          </label>
          <button className="acao primario" disabled={ocupado} style={{ alignSelf: "end" }}>
            Criar feed
          </button>
        </form>
        <p className="nota-driver">
          Quem tem o endereço lê a agenda, sem senha. Vai colar num calendário compartilhado?
          Escolha <em>só "Ocupado"</em>. Vazou? Revogue — o endereço morre na hora.
        </p>
      </div>

      {/* ── Calendly (RF-16) ───────────────────────────────────────────── */}
      <div className="cartao">
        <h2 className="bloco">Importar do Calendly</h2>
        <p style={{ fontSize: 14, color: "var(--fg-muted)", marginBottom: 14 }}>
          Para quem está migrando: o que for marcado no Calendly aparece aqui e ocupa o horário.
          Mão única — remarcar e cancelar continuam acontecendo lá, e o próximo aviso reflete
          aqui.
        </p>
        {calendly?.ativo && (
          <>
            <p style={{ fontSize: 14 }}>
              Ativo · entra como <strong>{servicos.find((s) => s.id === calendly.service_id)?.nome}</strong>{" "}
              em <strong>{nomeRecurso(calendly.resource_id)}</strong>
            </p>
            <p className="mono" style={{ fontSize: 12, margin: "6px 0 12px" }}>
              {calendly.webhook_url}
            </p>
            <BotaoConfirmar
              rotulo="Desligar importação"
              confirmacao="Desligar? Os compromissos já importados ficam."
              desabilitado={ocupado}
              onConfirmar={() =>
                agir(() => api.delete("/integracoes/calendly"), "Importação desligada")
              }
            />
          </>
        )}
        <form onSubmit={salvarCalendly} style={{ marginTop: calendly?.ativo ? 18 : 0 }}>
          <div className="formulario-linha">
            <label className="campo">
              Entra como serviço
              <select
                value={calendlyForm.servico}
                onChange={(e) => setCalendlyForm({ ...calendlyForm, servico: e.target.value })}
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
              Ocupa o recurso
              <select
                value={calendlyForm.recurso}
                onChange={(e) => setCalendlyForm({ ...calendlyForm, recurso: e.target.value })}
                required
              >
                {recursos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.nome}
                  </option>
                ))}
              </select>
            </label>
            <label className="campo">
              Chave de assinatura do webhook
              <input
                type="password"
                value={calendlyForm.chave}
                onChange={(e) => setCalendlyForm({ ...calendlyForm, chave: e.target.value })}
                placeholder="a signing key que o Calendly mostra"
                required
              />
            </label>
          </div>
          <label style={{ display: "block", fontSize: 13, marginBottom: 10 }}>
            <input
              type="checkbox"
              checked={calendlyForm.lembretes}
              onChange={(e) => setCalendlyForm({ ...calendlyForm, lembretes: e.target.checked })}
            />{" "}
            Também mandar os nossos lembretes (o Calendly já manda os dele)
          </label>
          <button className="acao primario" disabled={ocupado || !calendlyForm.chave}>
            {calendly?.ativo ? "Atualizar" : "Ativar importação"}
          </button>
        </form>
        <p className="nota-driver">
          A chave é gravada cifrada e nunca volta nesta tela — se perder, gere outra no Calendly e
          salve de novo aqui.
        </p>
      </div>
    </>
  );
}
