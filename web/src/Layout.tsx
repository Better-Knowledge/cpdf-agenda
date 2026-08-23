import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { sessao } from "./api";
import { ToastProvider } from "./Toast";

export function Layout() {
  const navegar = useNavigate();
  const aba = ({ isActive }: { isActive: boolean }) => `aba${isActive ? " ativa" : ""}`;
  return (
    <ToastProvider>
      <header className="topo">
        <div className="marca">
          Agenda <em>Inteligente</em>
        </div>
        <nav className="abas">
          <NavLink to="/dia" className={aba}>
            Agenda do dia
          </NavLink>
          <NavLink to="/servicos" className={aba}>
            Serviços
          </NavLink>
          <NavLink to="/grade" className={aba}>
            Grade e bloqueios
          </NavLink>
        </nav>
        <div className="canto">
          <span>Painel do prestador</span>
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
      </header>
      <main className="folha">
        <Outlet />
      </main>
    </ToastProvider>
  );
}
