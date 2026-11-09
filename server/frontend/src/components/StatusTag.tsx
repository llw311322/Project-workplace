import { STATUS_MAP, type DocumentStatus } from '@/utils/status';

/**
 * 状态标签组件：根据状态渲染不同颜色徽章
 */
export default function StatusTag({ status }: { status: DocumentStatus }) {
  const meta = STATUS_MAP[status];
  if (!meta) return <span className="badge bg-slate-100 text-slate-600">{status}</span>;
  return <span className={`badge ${meta.color}`}>{meta.label}</span>;
}
