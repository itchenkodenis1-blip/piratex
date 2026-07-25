import { Navigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0C0C0C] flex items-center justify-center">
        <span className="text-zinc-500 text-sm">Загрузка...</span>
      </div>
    );
  }

  if (!user || !user.is_admin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
