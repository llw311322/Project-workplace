import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import service from '@/api/request';

/**
 * 单据提交表单页：
 *  - 申领标题
 *  - 货品明细列表（名称/规格/数量/单价，可增删行）
 *  - 备注
 *  - 按钮：保存草稿 / 提交 / AI 摘要 / AI 校验
 */

interface ItemRow {
  id: string;
  name: string;
  spec: string;
  qty: number;
  price: number;
}

const newRow = (): ItemRow => ({
  id: Math.random().toString(36).slice(2),
  name: '',
  spec: '',
  qty: 1,
  price: 0,
});

export default function DocumentForm() {
  const [title, setTitle] = useState('');
  const [remark, setRemark] = useState('');
  const [items, setItems] = useState<ItemRow[]>([newRow()]);
  const [aiSummary, setAiSummary] = useState('');
  const [aiCheckResult, setAiCheckResult] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const totalAmount = items.reduce((s, it) => s + (Number(it.qty) || 0) * (Number(it.price) || 0), 0);

  // 货品明细行操作
  const addRow = () => setItems((prev) => [...prev, newRow()]);
  const removeRow = (id: string) =>
    setItems((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));
  const updateRow = (id: string, patch: Partial<ItemRow>) =>
    setItems((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  // 构建提交 payload（去掉前端内部的 id）
  const buildPayload = () => ({
    title,
    remark,
    items: items.map(({ id: _id, ...rest }) => rest),
  });

  // 保存 / 提交
  const submit = async (e: FormEvent, action: 'draft' | 'submit') => {
    e.preventDefault();
    if (!title.trim()) {
      alert('请填写申领标题');
      return;
    }
    setLoading(true);
    try {
      const resp = await service.post<{ id: string }>('/documents', {
        ...buildPayload(),
        action, // 后端约定：draft=草稿 / submit=提交审批
      });
      navigate(`/documents/${resp.data.id}`, { replace: true });
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // AI 摘要（流式也可以用 ssePost，这里先用普通 POST 示意）
  const handleAiSummary = async () => {
    if (!title.trim()) return alert('请先填写申领标题');
    setAiSummary('');
    try {
      const resp = await service.post<{ summary: string }>('/documents/ai/summary', buildPayload());
      setAiSummary(resp.data.summary);
    } catch (err) {
      alert((err as Error).message);
    }
  };

  // AI 校验
  const handleAiCheck = async () => {
    setAiCheckResult('校验中…');
    try {
      const resp = await service.post<{ result: string }>('/documents/ai/validate', buildPayload());
      setAiCheckResult(resp.data.result);
    } catch (err) {
      setAiCheckResult(`校验失败：${(err as Error).message}`);
    }
  };

  return (
    <div className="card">
      <form onSubmit={(e) => submit(e, 'submit')}>
        <div className="card-header flex items-center justify-between">
          <div>
            <div className="card-title">新建货品申领单</div>
            <div className="mt-1 text-xs text-slate-500">
              请填写货品明细，可使用右侧 AI 辅助按钮生成摘要 / 校验合规性
            </div>
          </div>
        </div>

        <div className="card-body space-y-5">
          {/* 基础字段 */}
          <div>
            <label className="label">申领标题 *</label>
            <input
              className="input"
              placeholder="如：研发部 Q4 办公设备采购"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* 货品明细 */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="label mb-0">货品明细</label>
              <button
                type="button"
                className="btn-outline text-xs"
                onClick={addRow}
              >
                + 新增一行
              </button>
            </div>

            <div className="overflow-hidden rounded-md border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">货品名称</th>
                    <th className="px-3 py-2 text-left font-medium">规格</th>
                    <th className="w-28 px-3 py-2 text-left font-medium">数量</th>
                    <th className="w-28 px-3 py-2 text-left font-medium">单价 (¥)</th>
                    <th className="w-24 px-3 py-2 text-left font-medium">小计</th>
                    <th className="w-20 px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => {
                    const subtotal = (Number(it.qty) || 0) * (Number(it.price) || 0);
                    return (
                      <tr key={it.id} className="border-t border-slate-100">
                        <td className="px-3 py-2">
                          <input
                            className="input"
                            value={it.name}
                            onChange={(e) => updateRow(it.id, { name: e.target.value })}
                            placeholder="如：MacBook Pro"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            className="input"
                            value={it.spec}
                            onChange={(e) => updateRow(it.id, { spec: e.target.value })}
                            placeholder="如：14寸 M3 Pro"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            className="input"
                            type="number"
                            min={1}
                            value={it.qty}
                            onChange={(e) =>
                              updateRow(it.id, { qty: Number(e.target.value) })
                            }
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            className="input"
                            type="number"
                            min={0}
                            step="0.01"
                            value={it.price}
                            onChange={(e) =>
                              updateRow(it.id, { price: Number(e.target.value) })
                            }
                          />
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          ¥ {subtotal.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            className="btn-ghost text-xs text-red-500 hover:bg-red-50"
                            onClick={() => removeRow(it.id)}
                            disabled={items.length === 1}
                          >
                            删除
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="bg-slate-50 text-slate-700">
                  <tr>
                    <td colSpan={4} className="px-3 py-2 text-right font-medium">
                      合计：
                    </td>
                    <td className="px-3 py-2 font-semibold text-indigo-700">
                      ¥ {totalAmount.toFixed(2)}
                    </td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* 备注 */}
          <div>
            <label className="label">备注</label>
            <textarea
              className="textarea"
              placeholder="其他补充说明，如用途、期望交付时间…"
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
            />
          </div>

          {/* AI 结果展示 */}
          {(aiSummary || aiCheckResult) && (
            <div className="grid gap-4 md:grid-cols-2">
              {aiSummary && (
                <div className="rounded-md border border-indigo-100 bg-indigo-50/60 p-3">
                  <div className="mb-1 text-xs font-medium text-indigo-700">AI 摘要</div>
                  <div className="text-sm text-slate-700 whitespace-pre-wrap">{aiSummary}</div>
                </div>
              )}
              {aiCheckResult && (
                <div className="rounded-md border border-emerald-100 bg-emerald-50/60 p-3">
                  <div className="mb-1 text-xs font-medium text-emerald-700">AI 校验</div>
                  <div className="text-sm text-slate-700 whitespace-pre-wrap">{aiCheckResult}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="card-footer">
          {/* 先调用草稿按钮：独立于 submit */}
          <button
            type="button"
            className="btn-outline"
            onClick={(e) => submit(e as unknown as FormEvent, 'draft')}
            disabled={loading}
          >
            保存草稿
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={handleAiSummary}
            disabled={loading}
          >
            ✨ AI 摘要
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={handleAiCheck}
            disabled={loading}
          >
            🛡 AI 校验
          </button>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? '处理中…' : '提交审批'}
          </button>
        </div>
      </form>
    </div>
  );
}
