interface PaginationProps {
  page: number;         // 当前页（从 1 开始）
  pageSize: number;     // 每页条数
  total: number;        // 总条数
  onChange: (page: number) => void;
}

/**
 * 分页组件：上一页 / 页码 / 下一页
 */
export default function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // 简易页码：只显示当前页左右各 1 个
  const pages: number[] = [];
  const start = Math.max(1, page - 1);
  const end = Math.min(totalPages, start + 2);
  for (let i = start; i <= end; i++) pages.push(i);

  const cls = (active: boolean) =>
    `h-8 min-w-[2rem] px-2 rounded-md text-sm inline-flex items-center justify-center transition-colors ${
      active
        ? 'bg-indigo-600 text-white'
        : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-100'
    }`;

  return (
    <div className="flex items-center justify-between">
      <div className="text-sm text-slate-500">
        共 {total} 条 · 第 {page} / {totalPages} 页
      </div>
      <div className="flex items-center gap-1">
        <button
          className={cls(false)}
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          上一页
        </button>
        {pages.map((p) => (
          <button key={p} className={cls(p === page)} onClick={() => onChange(p)}>
            {p}
          </button>
        ))}
        <button
          className={cls(false)}
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
