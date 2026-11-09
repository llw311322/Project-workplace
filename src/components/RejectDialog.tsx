import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'

interface Props {
  open: boolean
  loading?: boolean
  onCancel: () => void
  onConfirm: (comment: string) => void | Promise<void>
}

/** 驳回意见弹窗：驳回必须填写意见（与后端校验规则一致） */
export function RejectDialog({ open, loading, onCancel, onConfirm }: Props) {
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setComment('')
      setError('')
    }
  }, [open])

  if (!open) return null

  const confirm = async () => {
    if (!comment.trim()) {
      setError('驳回意见为必填项')
      return
    }
    await onConfirm(comment.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
        }}
      >
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-base font-semibold text-ink">驳回单据</h3>
          <button type="button" onClick={onCancel} className="rounded-lg p-1 text-faint hover:bg-field hover:text-ink-2">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-4 text-[13px] text-muted">
          单据将退回提交人修改，驳回意见会记入审批历史并通知提交人。
        </p>

        <Textarea
          autoFocus
          value={comment}
          onChange={(e) => {
            setComment(e.target.value)
            if (e.target.value.trim()) setError('')
          }}
          placeholder="请填写驳回意见（必填），如：数量与上月消耗不符，请核对后重新提交"
          className={error ? 'border-[#EF4444] focus:border-[#EF4444] focus:ring-[#EF4444]/20' : ''}
        />
        {error && <p className="mt-1.5 text-xs text-[#B91C1C]">{error}</p>}

        <div className="mt-4 flex justify-end gap-2.5">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            取消
          </Button>
          <Button variant="danger" className="bg-[#DC2626] text-white hover:bg-[#B91C1C]" onClick={confirm} disabled={loading}>
            {loading ? '提交中…' : '确认驳回'}
          </Button>
        </div>
      </div>
    </div>
  )
}
