import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, sessao } from "../api";
import { ErroAviso } from "../ErroAviso";

/** T-01, fase 1 do conector: chave de acesso da organização (X-Agent-Key).
 *  Quando o Supabase Auth entrar (fase 2), esta tela vira o login de e-mail. */
export function Entrar() {
  const [chave, setChave] = useState("");
  const [erro, setErro] = useState<unknown>(null);
  const [validando, setValidando] = useState(false);
  const navegar = useNavigate();

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    setValidando(true);
    setErro(null);
    sessao.entrar(chave.trim());
    try {
      await api.get("/resources"); // valida a chave contra a API
      navegar("/dia");
    } catch (e) {
      sessao.sair();
      setErro(
        e instanceof ApiError
          ? e
          : new ApiError(
              {
                code: "ERRO",
                message: "Chave não reconhecida.",
                hint: "Peça a chave de acesso da sua organização a quem administra o sistema.",
                retryable: true,
              },
              401,
            ),
      );
    } finally {
      setValidando(false);
    }
  }

  return (
    <div className="entrar">
      <form className="cartao" onSubmit={entrar}>
        <h1>Agenda Inteligente</h1>
        <p className="subtitulo">Entre com a chave de acesso da sua organização.</p>
        <label className="campo">
          Chave de acesso
          <input
            type="password"
            value={chave}
            onChange={(e) => setChave(e.target.value)}
            autoFocus
            required
            placeholder="demo-alunos-…"
          />
        </label>
        <ErroAviso erro={erro} />
        <button className="acao" disabled={validando || !chave.trim()}>
          {validando ? "Conferindo…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
