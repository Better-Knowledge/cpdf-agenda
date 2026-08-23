// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Recurso, Servico, api } from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-04: cadastro e edição de serviços. Excluir é desativar (soft delete):
// agendamentos e histórico existentes ficam intactos — regra da API.
const FORM_VAZIO = {
  nome: "",
  duracao: 60,
  preco: "0.00",
  bufferAntes: 0,
  bufferDepois: 0,
  recursosExigidos: [] as string[],
};

export function Servicos() {
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [inativos, setInativos] = useState<Servico[]>([]);
  const [mostrarInativos, setMostrarInativos] = useState(false);
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [salvando, setSalvando] = useState(false);

  const [editando, setEditando] = useState<string | null>(null); // id em edição
  const [form, setForm] = useState(FORM_VAZIO);
  const avisar = usarToast();

  const carregar = useCallback(async () => {
    setServicos((await api.get<{ items: Servico[] }>("/services?limit=50")).items);
    setInativos((await api.get<{ items: Servico[] }>("/services?ativo=false&limit=50")).items);
    setRecursos((await api.get<{ items: Recurso[] }>("/resources")).items);
  }, []);

  useEffect(() => {
    carregar().catch(setErro);
  }, [carregar]);

  function editar(s: Servico) {
    setEditando(s.id);
    setForm({
      nome: s.nome,
      duracao: s.duracao_min,
      preco: s.preco,
      bufferAntes: s.buffer_antes_min,
      bufferDepois: s.buffer_depois_min,
      recursosExigidos: [], // vínculos atuais não vêm na listagem; vazio = não mexer
    });
  }

  async function agir(acao: () => Promise<unknown>, feito: string) {
    setSalvando(true);
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
      setSalvando(false);
    }
  }

  async function salvar(evento: FormEvent) {
    evento.preventDefault();
    const corpo = {
      nome: form.nome,
      duracao_min: form.duracao,
      preco: form.preco,
      buffer_antes_min: form.bufferAntes,
      buffer_depois_min: form.bufferDepois,
    };
    const ok = await agir(
      () =>
        editando
          ? api.patch(`/services/${editando}`, {
              ...corpo,
              // em edição, só substitui vínculos se algo foi marcado
              ...(form.recursosExigidos.length > 0 && { resource_ids: form.recursosExigidos }),
            })
          : api.post("/services", { ...corpo, resource_ids: form.recursosExigidos }),
      editando ? "Serviço salvo" : "Serviço cadastrado",
    );
    if (ok) {
      setForm(FORM_VAZIO);
      setEditando(null);
    }
  }

  const linha = (s: Servico, ativo: boolean) => (
    <tr key={s.id} style={ativo ? undefined : { color: "var(--fg-soft)" }}>
      <td>
        <strong>{s.nome}</strong>
      </td>
      <td className="mono">{s.duracao_min} min</td>
      <td className="valor">R$ {s.preco}</td>
      <td className="mono">
        {s.buffer_antes_min} / {s.buffer_depois_min} min
      </td>
      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
        {ativo ? (
          <>
            <button className="acao miuda" onClick={() => editar(s)}>
              Editar
            </button>{" "}
            <BotaoConfirmar
              miudo
              rotulo="Desativar"
              confirmacao="Desativar?"
              desabilitado={salvando}
              onConfirmar={() =>
                agir(() => api.delete(`/services/${s.id}`), "Serviço desativado — fora da oferta")
              }
            />
          </>
        ) : (
          <button
            className="acao miuda"
            disabled={salvando}
            onClick={() =>
              agir(() => api.patch(`/services/${s.id}`, { ativo: true }), "Serviço reativado")
            }
          >
            Reativar
          </button>
        )}
      </td>
    </tr>
  );

  return (
    <>
      <h1>
        Seus <em>serviços</em>
      </h1>
      <p className="subtitulo">
        O que a sua agenda oferece — duração, preço e folga entre atendimentos. Desativar um
        serviço tira ele da oferta sem mexer nos agendamentos já feitos.
      </p>
      <ErroAviso erro={erro} />

      <div className="cartao" style={{ marginBottom: 20 }}>
        {servicos.length === 0 && inativos.length === 0 ? (
          <div className="vazio">Nenhum serviço ainda — cadastre o primeiro abaixo.</div>
        ) : (
          <table className="lista">
            <thead>
              <tr>
                <th>Serviço</th>
                <th>Duração</th>
                <th>Preço</th>
                <th>Folga antes/depois</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {servicos.map((s) => linha(s, true))}
              {mostrarInativos && inativos.map((s) => linha(s, false))}
            </tbody>
          </table>
        )}
        {inativos.length > 0 && (
          <label style={{ display: "block", marginTop: 10, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={mostrarInativos}
              onChange={(e) => setMostrarInativos(e.target.checked)}
            />{" "}
            Mostrar desativados ({inativos.length})
          </label>
        )}
      </div>

      <form className="cartao" onSubmit={salvar}>
        <h2 className="bloco">{editando ? "Editar serviço" : "Novo serviço"}</h2>
        <div className="formulario-linha">
          <label className="campo">
            Nome
            <input
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
              required
            />
          </label>
          <label className="campo">
            Duração (min)
            <input
              type="number"
              min={5}
              step={5}
              value={form.duracao}
              onChange={(e) => setForm({ ...form, duracao: Number(e.target.value) })}
            />
          </label>
          <label className="campo">
            Preço (R$)
            <input
              value={form.preco}
              onChange={(e) => setForm({ ...form, preco: e.target.value })}
              placeholder="80.00"
            />
          </label>
          <label className="campo">
            Folga antes (min)
            <input
              type="number"
              min={0}
              step={5}
              value={form.bufferAntes}
              onChange={(e) => setForm({ ...form, bufferAntes: Number(e.target.value) })}
            />
          </label>
          <label className="campo">
            Folga depois (min)
            <input
              type="number"
              min={0}
              step={5}
              value={form.bufferDepois}
              onChange={(e) => setForm({ ...form, bufferDepois: Number(e.target.value) })}
            />
          </label>
        </div>
        {recursos.length > 0 && (
          <fieldset style={{ border: "none", margin: "12px 0" }}>
            <legend className="campo" style={{ marginBottom: 6 }}>
              {editando ? "Substituir recursos exigidos (opcional)" : "Exige quais recursos?"}
            </legend>
            {recursos.map((r) => (
              <label key={r.id} style={{ marginRight: 16, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={form.recursosExigidos.includes(r.id)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      recursosExigidos: e.target.checked
                        ? [...form.recursosExigidos, r.id]
                        : form.recursosExigidos.filter((id) => id !== r.id),
                    })
                  }
                />{" "}
                {r.nome}
              </label>
            ))}
          </fieldset>
        )}
        {editando && (
          <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 10 }}>
            Mudar a duração vale para novos horários — agendamentos já feitos não mudam.
          </p>
        )}
        <button className="acao primario" disabled={salvando || !form.nome.trim()}>
          {salvando ? "Salvando…" : editando ? "Salvar alterações" : "Cadastrar serviço"}
        </button>{" "}
        {editando && (
          <button
            type="button"
            className="acao"
            onClick={() => {
              setEditando(null);
              setForm(FORM_VAZIO);
            }}
          >
            Cancelar edição
          </button>
        )}
      </form>
    </>
  );
}
