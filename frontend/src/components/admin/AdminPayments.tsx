import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminListPayments } from "../../api/client";
import type { AdminPayment } from "../../types";
import MaskedPII from "./MaskedPII";

const STATUS_COLORS: Record<string, string> = {
  succeeded: "bg-green-900/50 text-green-300",
  pending: "bg-yellow-900/50 text-yellow-300",
  cancelled: "bg-zinc-700/50 text-zinc-400",
  refunded: "bg-blue-900/50 text-blue-300",
};

const STATUS_LABELS: Record<string, string> = {
  succeeded: "Оплачен",
  pending: "Ожидание",
  cancelled: "Отменён",
  refunded: "Возврат",
};

const PROVIDER_LABELS: Record<string, string> = {
  yookassa: "ЮKassa",
  stripe: "Stripe",
};

const METHOD_LABELS: Record<string, string> = {
  bank_card: "Карта",
  sbp: "СБП",
  yoomoney: "ЮMoney",
  card: "Card",
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-zinc-700/50 text-zinc-400";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function ProviderBadge({ provider }: { provider: string | null }) {
  if (!provider) return <span className="text-zinc-600">—</span>;
  const colors: Record<string, string> = {
    yookassa: "text-purple-400",
    stripe: "text-indigo-400",
  };
  return (
    <span className={`text-xs font-medium ${colors[provider] ?? "text-zinc-400"}`}>
      {PROVIDER_LABELS[provider] ?? provider}
    </span>
  );
}

function formatDate(dt: string) {
  return new Date(dt).toLocaleDateString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function formatAmount(kopecks: number, currency: string): string {
  const amount = kopecks / 100;
  if (currency === "RUB") {
    return amount.toLocaleString("ru-RU") + " \u20BD";
  }
  if (currency === "EUR") {
    return "\u20AC" + amount.toLocaleString("en-US", { minimumFractionDigits: 2 });
  }
  return amount.toLocaleString() + " " + currency;
}

export function AdminPayments() {
  const navigate = useNavigate();
  const [payments, setPayments] = useState<AdminPayment[]>([]);
  const [total, setTotal] = useState(0);
  const [totalAll, setTotalAll] = useState(0);
  const [totalSucceeded, setTotalSucceeded] = useState(0);
  const [totalRub, setTotalRub] = useState(0);
  const [totalEur, setTotalEur] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(query);
      setPage(1);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  function load() {
    setLoading(true);
    adminListPayments({
      status: statusFilter || undefined,
      provider: providerFilter || undefined,
      q: debouncedQuery || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setPayments(res.items);
        setTotal(res.total);
        setTotalAll(res.total_all);
        setTotalSucceeded(res.total_succeeded);
        setTotalRub(res.total_rub_kopecks);
        setTotalEur(res.total_eur_cents);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [statusFilter, providerFilter, debouncedQuery, page]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">Платежи</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="text-xs text-zinc-500 mb-1">Всего платежей</div>
          <div className="text-lg font-medium text-zinc-100">{total}</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="text-xs text-zinc-500 mb-1">Успешных</div>
          <div className="text-lg font-medium text-green-400">{totalSucceeded}</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="text-xs text-zinc-500 mb-1">Выручка</div>
          <div className="text-lg font-medium text-zinc-100">
            {formatAmount(totalRub, "RUB")}
          </div>
          {totalEur > 0 && (
            <div className="text-sm text-zinc-400 mt-0.5">
              + {formatAmount(totalEur, "EUR")}
            </div>
          )}
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="text-xs text-zinc-500 mb-1">Конверсия</div>
          <div className="text-lg font-medium text-zinc-100">
            {totalAll > 0 ? ((totalSucceeded / totalAll) * 100).toFixed(1) + "%" : "—"}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 pb-4 border-b border-zinc-800 flex-wrap">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все статусы</option>
          <option value="succeeded">Оплачен</option>
          <option value="pending">Ожидание</option>
          <option value="cancelled">Отменён</option>
          <option value="refunded">Возврат</option>
        </select>

        <select
          value={providerFilter}
          onChange={(e) => { setProviderFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все провайдеры</option>
          <option value="yookassa">ЮKassa</option>
          <option value="stripe">Stripe</option>
        </select>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по email..."
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500 w-64 placeholder:text-zinc-600"
        />

        <span className="ml-auto text-xs text-zinc-500">{total} платежей</span>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {["Пользователь", "Сумма", "Провайдер", "Метод", "Статус", "Описание", "Дата создания", "Дата оплаты"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="px-4 py-3 text-xs max-w-[180px]">
                      <button
                        onClick={() => navigate(`/admin/users/${p.user_id}`)}
                        className="truncate block text-left text-zinc-400 hover:text-zinc-100 transition-colors"
                        title={p.user_email || p.user_id}
                      >
                        {p.user_name ? <MaskedPII type="name" value={p.user_name} /> : p.user_email ? <MaskedPII type="email" value={p.user_email} /> : <span className="text-zinc-600">Аноним</span>}
                      </button>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`text-sm font-medium ${p.status === "succeeded" ? "text-green-400" : "text-zinc-300"}`}>
                        {formatAmount(p.amount_kopecks, p.currency)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ProviderBadge provider={p.payment_provider} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-400">
                      {p.payment_method ? (METHOD_LABELS[p.payment_method] ?? p.payment_method) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={p.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-zinc-500 max-w-[200px] truncate" title={p.description || ""}>
                      {p.description || "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {formatDate(p.created_at)}
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      {p.paid_at ? (
                        <span className="text-green-400/70">{formatDate(p.paid_at)}</span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}

                {payments.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-600 text-sm">
                      Нет платежей
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center gap-4 mt-4 pt-4 border-t border-zinc-800">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                &larr; Назад
              </button>
              <span className="text-xs text-zinc-500">
                Страница {page} из {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                Вперёд &rarr;
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
