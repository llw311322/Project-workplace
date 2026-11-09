import { cn } from '@/lib/utils'
import type { ClaimStatus } from '@/lib/types'

export const STATUS_META: Record<
  ClaimStatus,
  { label: string; chip: string; dot: string; text: string }
> = {
  draft: { label: '草稿', chip: 'bg-[#F3F4F6]', dot: 'bg-[#9CA3AF]', text: 'text-[#4B5563]' },
  submitted: { label: '待审批', chip: 'bg-[#FEF3C7]', dot: 'bg-[#F59E0B]', text: 'text-[#B45309]' },
  approving: { label: '审批中', chip: 'bg-primary-light', dot: 'bg-primary', text: 'text-primary' },
  approved: { label: '审批通过', chip: 'bg-[#DCFCE7]', dot: 'bg-[#22C55E]', text: 'text-[#15803D]' },
  rejected: { label: '已驳回', chip: 'bg-[#FEE2E2]', dot: 'bg-[#EF4444]', text: 'text-[#B91C1C]' },
}

export function StatusBadge({ status, className }: { status: ClaimStatus; className?: string }) {
  const meta = STATUS_META[status]
  return (
    <span
      className={cn(
        'inline-flex h-6 w-fit items-center gap-1.5 rounded-full px-2 text-xs font-medium',
        meta.chip,
        meta.text,
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} />
      {meta.label}
    </span>
  )
}
