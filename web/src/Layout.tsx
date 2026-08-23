import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { sessao } from "./api";

export function Layout() {
  const navegar = useNavigate();
  return (
    <div className="aplicacao">
      <nav className="trilho">
        <div className="marca">
          Agenda Inteligente
          <small>painel do prestador</small>
        </div>
        <NavLink to="/dia" className={({ isActive }) => (isActive ? "ativa" : "")}>
          Agenda do dia
        </NavLink>
        <NavLink to="/servicos" className={({ isActive }) => (isActive ? "ativa" : "")}>
          Serviços
        </NavLink>
        <NavLink to="/grade" className={({ isActive }) => (isActive ? "ativa" : "")}>
          Grade e bloqueios
        </NavLink>
        <div className="rodape">
          A operação acontece por conversa — aqui você configura e supervisiona.{" "}
          <button
            type="button"
            onClick={() => {
              sessao.sair();
              navegar("/entrar");
            }}
          >
            Sair
          </button>
        </div>
      </nav>
      <main className="folha">
        <Outlet />
      </main>
    </div>
  );
}
