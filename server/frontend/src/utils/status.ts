/**
 * 单据状态映射：中文文案 + 颜色（配合 StatusTag 使用）
 */

export type DocumentStatus = 'draft' | 'pending' | 'approved' | 'rejected';

export interface StatusMeta {
  label: string;
  color: string; // tailwind 类：bg-xxx text-xxx
}

export const STATUS_MAP: Record<DocumentStatus, StatusMeta> = {
  draft: {
    label: '草稿',
    color: 'bg-slate-100 text-slate-600',
  },
  pending: {
    label: '待审批',
    color: 'bg-amber-100 text-amber-700',
  },
  approved: {
    label: '已通过',
    color: 'bg-emerald-100 text-emerald-700',
  },
  rejected: {
    label: '已驳回',
    color: 'bg-red-100 text-red-700',
  },
};

/** 状态枚举 -> 中文文案 */
export function statusLabel(status: DocumentStatus): string {
  return STATUS_MAP[status]?.label ?? status;
}

/** 所有可筛选状态 */
export const STATUS_OPTIONS: Array<{ value: DocumentStatus | 'all'; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
];
