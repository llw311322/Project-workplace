import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import service from '@/api/request';
import Pagination from '@/components/Pagination';
import StatusTag from '@/components/StatusTag';
import { STATUS_OPTIONS, type DocumentStatus } from '@/utils/status';

/**
 * 单据列表页：表格 + 分页 + 状态筛选 + 提交人筛选
 */

interface DocumentRow {
  id: string;
  title: string;
  submitter: string;
  status: DocumentStatus;
  created_at: string;
}

export default function DocumentList() {
  const [list, setList] = useState<DocumentRow[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<DocumentStatus | 'all'>('all');
  const [submitter, setSubmitter] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await service.get<{ items: DocumentRow[]; total: number }>(
        '/documents',
        {
          params: {
            page,
            page_size: pageSize,
            status: status === 'all' ? undefined : status,
            submitter: submitter || undefined,
          },
        },
      );
      setList(resp.data.items);
      setTotal(resp.data.total);
    } catch (err) {
      // 简单提示
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // 分页 / 筛选变化都触发 reload
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, status, submitter]);

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <div>
          <div className="card-title">单据列表</div>
          <div className="mt-1 text-xs text-slate-500">
            查看和管理您提交的所有单据
          </div>
        </div>
        <Link to="/documents/new" className="btn-primary">
          + 新建单据
        </Link>
      </div>

      {/* 筛选区 */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-600">状态：</span>
          <select
            className="select w-36"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as DocumentStatus | 'all');
              setPage(1);
            }}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-600">提交人：</span>
          <input
            className="input w-36"
            placeholder="输入姓名搜索"
            value={submitter}
            onChange={(e) => {
              setSubmitter(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>

      {/* 表格 */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-5 py-3 text-left font-medium">标题</th>
              <th className="px-5 py-3 text-left font-medium">提交人</th>
              <th className="px-5 py-3 text-left font-medium">状态</th>
              <th className="px-5 py-3 text-left font-medium">创建时间</th>
              <th className="px-5 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-slate-400">
                  暂无数据
                </td>
              </tr>
            ) : (
              list.map((row) => (
                <tr
                  key={row.id}
                  className="border-t border-slate-100 hover:bg-slate-50/50"
                >
                  <td className="px-5 py-3 text-slate-800">{row.title}</td>
                  <td className="px-5 py-3 text-slate-600">{row.submitter}</td>
                  <td className="px-5 py-3">
                    <StatusTag status={row.status} />
                  </td>
                  <td className="px-5 py-3 text-slate-500">{row.created_at}</td>
                  <td className="px-5 py-3 text-right">
                    <Link
                      to={`/documents/${row.id}`}
                      className="text-indigo-600 hover:underline"
                    >
                      查看详情
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      <div className="card-footer justify-start">
        <Pagination page={page} pageSize={pageSize} total={total} onChange={setPage} />
      </div>
    </div>
  );
}
