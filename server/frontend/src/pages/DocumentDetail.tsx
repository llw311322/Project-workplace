import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import service from '@/api/request';
import StatusTag from '@/components/StatusTag';
import ApprovalTimeline, { type ApprovalNode } from '@/components/ApprovalTimeline';
import AgentChat from '@/components/AgentChat';
import type { DocumentStatus } from '@/utils/status';

/**
 * 单据详情页：
 *  - 左侧上：表单只读展示
 *  - 左侧下：审批历史时间线
 *  - 右侧：Agent 对话面板
 */

interface DocumentDetailResp {
  id: string;
  title: string;
  submitter: string;
  status: DocumentStatus;
  created_at: string;
  remark?: string;
  items: Array<{ name: string; spec: string; qty: number; price: number }>;
  timeline: ApprovalNode[];
}

export default function DocumentDetail() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentDetailResp | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const resp = await service.get<DocumentDetailResp>(`/documents/${id}`);
        setDoc(resp.data);
      } catch (err) {
        alert((err as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return <div className="text-sm text-slate-400">加载中…</div>;
  }
  if (!doc) {
    return <div className="text-sm text-slate-400">单据不存在</div>;
  }

  const total = doc.items.reduce((s, it) => s + it.qty * it.price, 0);

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-4">
      {/* ===== 左侧：表单详情 + 审批时间线 ===== */}
      <div className="flex flex-1 flex-col gap-4 overflow-auto">
        {/* 表单详情 */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="card-title">{doc.title}</span>
                <StatusTag status={doc.status} />
              </div>
              <div className="mt-1 text-xs text-slate-500">
                提交人：{doc.submitter} · 创建于 {doc.created_at}
              </div>
            </div>
            <Link to="/documents" className="btn-outline">
              ← 返回列表
            </Link>
          </div>
          <div className="card-body space-y-4">
            {/* 货品明细 */}
            <div>
              <div className="label">货品明细</div>
              <div className="overflow-hidden rounded-md border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">货品名称</th>
                      <th className="px-3 py-2 text-left font-medium">规格</th>
                      <th className="px-3 py-2 text-left font-medium">数量</th>
                      <th className="px-3 py-2 text-left font-medium">单价</th>
                      <th className="px-3 py-2 text-left font-medium">小计</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.items.map((it, idx) => (
                      <tr key={idx} className="border-t border-slate-100">
                        <td className="px-3 py-2">{it.name}</td>
                        <td className="px-3 py-2 text-slate-500">{it.spec}</td>
                        <td className="px-3 py-2">{it.qty}</td>
                        <td className="px-3 py-2">¥ {it.price.toFixed(2)}</td>
                        <td className="px-3 py-2">
                          ¥ {(it.qty * it.price).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-50 text-slate-700">
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-right font-medium">
                        合计：
                      </td>
                      <td className="px-3 py-2 font-semibold text-indigo-700">
                        ¥ {total.toFixed(2)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* 备注 */}
            {doc.remark && (
              <div>
                <div className="label">备注</div>
                <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700 whitespace-pre-wrap">
                  {doc.remark}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 审批历史时间线 */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">审批历史</div>
          </div>
          <div className="card-body">
            <ApprovalTimeline nodes={doc.timeline} />
          </div>
        </div>
      </div>

      {/* ===== 右侧：Agent 对话面板 ===== */}
      <div className="w-96 shrink-0 card flex flex-col overflow-hidden">
        <div className="card-header">
          <div className="card-title flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500"></span>
            智能审批助手
          </div>
          <div className="mt-1 text-xs text-slate-500">
            可以问关于这张单据的任何问题
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          <AgentChat contextId={doc.id} />
        </div>
      </div>
    </div>
  );
}
