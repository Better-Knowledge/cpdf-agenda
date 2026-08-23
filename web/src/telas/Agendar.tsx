// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { AgendamentoPublico, ApiError, PaginaPublica, Slot, publico } from "../api";

// P-01: a página pública de auto-agendamento (RF-13).
//
// É a única tela do produto que uma pessoa de fora abre, e a única que roda
// **sem credencial**. Por isso ela não importa nada do painel: nem a chave de
// acesso, nem o menu, nem qualquer rota autenticada. O que ela mostra é o
// mínimo — serviço, duração, horários livres — porque tudo além disso seria
// contar a agenda de alguém para quem tem só um link.

function diasSeguintes(quantos: number): string[] {
  const hoje = new Date();
  return Array.from({ length: quantos }, (_, i) => {
    const d = new Date(hoje);
    d.setDate(d.getDate() + i);
    return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(d);
  });
}

function porExtenso(dataISO: string): string {
  const texto = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(`${dataISO}T12:00:00-03:00`));
  return texto.replace(".", "");
}

function hora(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function Agendar() {
  const { slug = "" } = useParams();
  const dias = diasSeguintes(14);
  const [pagina, setPagina] = useState<PaginaPublica | null>(null);
  const [dia, setDia] = useState(dias[0]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [escolhido, setEscolhido] = useState<Slot | null>(null);
  const [form, setForm] = useState({ nome: "", telefone: "" });
  const [pronto, setPronto] = useState<AgendamentoPublico | null>(null);
  const [erro, setErro] = useState<ApiError | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    publico
      .get<PaginaPublica>(`/publico/agendar/${slug}`)
      .then(setPagina)
      .catch((e) => setErro(e as ApiError))
      .finally(() => setCarregando(false));
  }, [slug]);

  useEffect(() => {
    if (!pagina) return;
    setEscolhido(null);
    const de = `${dia}T00:00:00-03:00`;
    const ate = `${dia}T23:59:59-03:00`;
    publico
      .get<Slot[]>(`/publico/agendar/${slug}/slots?from=${de}&to=${ate}&limit=50`)
      .then(setSlots)
      .catch((e) => setErro(e as ApiError));
  }, [dia, pagina, slug]);

  async function confirmar(evento: FormEvent) {
    evento.preventDefault();
    if (!escolhido) return;
    setErro(null);
    try {
      setPronto(
        await publico.post<AgendamentoPublico>(`/publico/agendar/${slug}`, {
          cliente_nome: form.nome,
          cliente_telefone: form.telefone,
          inicio: escolhido.inicio,
        }),
      );
    } catch (e) {
      setErro(e as ApiError);
      // Horário tomado no meio do caminho: a API já devolve as alternativas.
      if ((e as ApiError).erro?.code === "SLOT_INDISPONIVEL") setEscolhido(null);
    }
  }

  if (carregando) return <main className="publica">Carregando…</main>;

  if (pronto) {
    return (
      <main className="publica">
        <h1>Pronto!</h1>
        <p className="confirmado-grande">{pronto.label_humano}</p>
        <p>{pronto.mensagem}</p>
        <p className="rodape-publico">
          Precisa mudar? Responda a mensagem de confirmação no WhatsApp — remarcar por lá é mais
          rápido do que voltar aqui.
        </p>
      </main>
    );
  }

  if (!pagina) {
    return (
      <main className="publica">
        <h1>Este link não está disponível</h1>
        <p>{erro?.erro?.message ?? "O endereço pode ter mudado."}</p>
        <p className="rodape-publico">{erro?.erro?.hint}</p>
      </main>
    );
  }

  return (
    <main className="publica">
      <h1>{pagina.servico}</h1>
      <p className="subtitulo">
        {pagina.duracao_min} minutos · R$ {pagina.preco}
      </p>
      {pagina.aviso_caucao && <p className="aviso-caucao">{pagina.aviso_caucao}</p>}

      {erro && erro.erro?.code !== "NAO_ENCONTRADO" && (
        <div className="aviso-erro">
          {erro.erro.message}
          <span className="dica">{erro.erro.hint}</span>
        </div>
      )}

      <h2 className="bloco">Escolha o dia</h2>
      <div className="tiras-dias">
        {dias.map((d) => (
          <button
            key={d}
            type="button"
            className={`tira${d === dia ? " ativa" : ""}`}
            onClick={() => setDia(d)}
          >
            {porExtenso(d)}
          </button>
        ))}
      </div>

      <h2 className="bloco">Horários livres</h2>
      {slots.length === 0 ? (
        <p className="vazio">
          Nada livre neste dia. Tente outro — ou fale pelo WhatsApp, que a fila de espera avisa
          quando vagar.
        </p>
      ) : (
        <div className="tiras-horas">
          {slots.map((s) => (
            <button
              key={s.inicio}
              type="button"
              className={`tira${escolhido?.inicio === s.inicio ? " ativa" : ""}`}
              onClick={() => setEscolhido(s)}
            >
              {hora(s.inicio)}
            </button>
          ))}
        </div>
      )}

      {escolhido && (
        <form className="cartao" onSubmit={confirmar} style={{ marginTop: 24 }}>
          <h2 className="bloco">{escolhido.label_humano}</h2>
          <div className="formulario-linha">
            <label className="campo">
              Seu nome
              <input
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
                required
                minLength={2}
              />
            </label>
            <label className="campo">
              WhatsApp
              <input
                value={form.telefone}
                onChange={(e) => setForm({ ...form, telefone: e.target.value })}
                placeholder="+55 11 90000-0000"
                required
                minLength={8}
              />
            </label>
          </div>
          <p className="rodape-publico">
            Usamos seu nome e telefone só para confirmar e lembrar deste horário.
          </p>
          <button className="acao primario">Confirmar horário</button>
        </form>
      )}
    </main>
  );
}
