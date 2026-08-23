// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { ApiError } from "./api";

/** Mostra o erro do contrato do programa: message + hint (a dica de recuperação). */
export function ErroAviso({ erro }: { erro: unknown }) {
  if (!erro) return null;
  if (erro instanceof ApiError) {
    return (
      <div className="aviso-erro" role="alert">
        <strong>{erro.erro.message}</strong>
        {erro.erro.hint && <span className="dica">{erro.erro.hint}</span>}
      </div>
    );
  }
  return (
    <div className="aviso-erro" role="alert">
      <strong>Não foi possível falar com a API.</strong>
      <span className="dica">Confira sua conexão e tente de novo.</span>
    </div>
  );
}
