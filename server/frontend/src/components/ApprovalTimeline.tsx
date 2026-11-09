/**
 * 审批历史时间线：
 *   - 节点依次展示：提交 → 审批中 → 通过/驳回
 *   - 每个节点显示：操作人、动作、时间、备注
 */

export interface ApprovalNode {
  id: string;
  title: string;        // 节点标题：如 "提交" / "一级审批"
  operator: string;     // 操作人姓名
  action: string;       // 动作描述
  remark?: string;      // 备注
  time: string;         // 格式化时间字符串
  type: 'submit' | 'approve' | 'pass' | 'reject';
}

const typeColor: Record<ApprovalNode['type'], string> = {
  submit: 'bg-slate-400',
  approve: 'bg-indigo-500',
  pass: 'bg-emerald-500',
  reject: 'bg-red-500',
};

export default function ApprovalTimeline({ nodes }: { nodes: ApprovalNode[] }) {
  if (!nodes.length) {
    return <div className="text-sm text-slate-400">暂无审批记录</div>;
  }
  return (
    <ol className="relative border-l border-slate-200 pl-4">
      {nodes.map((n, idx) => (
        <li key={n.id} className={idx === nodes.length - 1 ? '' : 'mb-6'}>
          {/* 圆点 */}
          <span
            className={`absolute -left-1.5 mt-1 flex h-3 w-3 items-center justify-center rounded-full ring-4 ring-white ${typeColor[n.type]}`}
          />
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-800">{n.title}</span>
            <span className="text-xs text-slate-500">{n.time}</span>
          </div>
          <div className="mt-0.5 text-sm text-slate-600">
            {n.operator} · {n.action}
          </div>
          {n.remark && (
            <div className="mt-1 text-xs text-slate-500">备注：{n.remark}</div>
          )}
        </li>
      ))}
    </ol>
  );
}
